from django.core.mail import send_mail
from django.template import RequestContext, Context, Template
from django.template.loader import get_template
from django.http import HttpResponseRedirect, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.forms.models import model_to_dict
from django.shortcuts import render_to_response, get_object_or_404

from opensourcemusic.main.forms import *
from opensourcemusic.settings import MEDIA_URL, MEDIA_ROOT, CHAT_TIMEOUT

import simplejson as json
from datetime import datetime, timedelta
import string
import random

def json_response(data):
    return HttpResponse(json_dump(data), mimetype="text/plain")

def remove_unsafe_keys(hash, model):
    """
    look for UNSAFE_KEYS in the model. if it exists, delete all those entries
    from the hash.
    """
    if isinstance(model, User):
        check = (
            'password',
            'user_permissions',
            'is_user',
            'is_staff'
        )
    else:
        try:
            check = model.UNSAFE_KEYS
        except AttributeError:
            return

    for key in check:
        if hash.has_key(key):
            del hash[key]
        
def safe_model_to_dict(model_instance):
    hash = model_to_dict(model_instance)
    remove_unsafe_keys(hash, type(model_instance))
    return hash

def json_dthandler(obj):
    if isinstance(obj, datetime):
        return obj.strftime('%B %d, %Y %H:%M:%S')
    else:
        return None

def json_dump(obj):
    return json.dumps(obj, default=json_dthandler)
    
def activeUser(request):
    """
    touch the request's user if they are authenticated in order
    to update the last_activity field
    """
    if request.user.is_authenticated():
        request.user.get_profile().save() # set active date

def ajax_login_state(request):
    activeUser(request)

    # build the object
    data = {
        'user': {
            'is_authenticated': request.user.is_authenticated(),
        },
    }

    if request.user.is_authenticated():
        data['user'].update(safe_model_to_dict(request.user))
        data['user']['get_profile'] = safe_model_to_dict(request.user.get_profile())
        data['user']['get_profile']['get_points'] = request.user.get_profile().get_points()

    return json_response(data)

def user_logout(request):
    logout(request)
    return HttpResponseRedirect(request.GET.get('next', '/'))

def user_login(request):
    err_msg = ''
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(username=form.cleaned_data.get('username'), password=form.cleaned_data.get('password'))
            if user is not None:
                if user.is_active and user.get_profile().activated:
                    login(request, user)
                    return HttpResponseRedirect(form.cleaned_data.get('next_url'))
                else:
                    err_msg = 'Your account is not activated.'
            else:
                err_msg = 'Invalid login.'
    else:
        form = LoginForm(initial={'next_url': request.GET.get('next', '/')})
    return render_to_response('login.html', {'form': form, 'err_msg': err_msg }, context_instance=RequestContext(request))

def ajax_login(request):
    err_msg = ''
    success = False
    if request.method == 'POST':
        user = authenticate(username=request.POST.get('username', ''), password=request.POST.get('password', ''))
        if user is not None:
            if user.is_active and user.get_profile().activated:
                login(request, user)
                success = True
            else:
                err_msg = 'Your account is not activated.'
        else:
            err_msg = 'Invalid login.'
    else:
        err_msg = 'No login data supplied.'

    data = {
        'success': success,
        'err_msg': err_msg,
    }

    return json_response(data)

def ajax_logout(request):
    logout(request)

    data = {
        'success': True,
    }

    return json_response(data)

def python_date(js_date):
    """
    convert a javascript date to a python date
    format: Wed Apr 28 2010 04:20:43 GMT-0700 (MST)
    """
    return datetime.strptime(js_date[:24], "%a %b %d %Y %H:%M:%S")

def user_can_chat(room, user):
    if room.permission_type == OPEN:
        return True
    else:
        # user has to be signed in
        if not user.is_authenticated():
            return False

        if room.permission_type == WHITELIST:
            # user has to be on the whitelist
            if room.whitelist.filter(pk=user.get_profile().id).count() != 1:
                return False
        elif room.permission_type == BLACKLIST:
            # user is blocked if he is on the blacklist 
            if room.blacklist.filter(pk=user.get_profile().id).count() == 1:
                return False

        return True

def ajax_chat(request):
    latest_check = request.GET.get('latest_check', 'null')
    room_id = request.GET.get('room', 0)
    try:
        room_id = int(room_id)
    except:
        room_id = 0
    room = get_object_or_404(ChatRoom, id=room_id)

    # make sure user has permission to be in this room
    data = {
        'user': {
            'is_authenticated': request.user.is_authenticated(),
            'has_permission': False,
        },
        'room': safe_model_to_dict(room),
        'messages': [],
    }

    if request.user.is_authenticated():
        data['user']['get_profile'] = safe_model_to_dict(request.user.get_profile())
        data['user']['username'] = request.user.username

    data['user']['has_permission'] = user_can_chat(room, request.user)

    def add_to_message(msg):
        d = safe_model_to_dict(msg)
        d['author'] = safe_model_to_dict(msg.author)
        d['author']['username'] = msg.author.user.username
        d['timestamp'] = msg.timestamp
        return d

    if latest_check == 'null':
        # get entire log for this chat.
        data['messages'] = [add_to_message(x) for x in ChatMessage.objects.filter(room=room).order_by('timestamp')]
    else:
        check_date = python_date(latest_check)
        data['messages'] = [add_to_message(x) for x in ChatMessage.objects.filter(room=room, timestamp__gt=check_date).order_by('timestamp')]

    if request.user.is_authenticated():
        # mark an appearance in the ChatRoom
        appearances = Appearance.objects.filter(person=request.user.get_profile(), room=room)
        if appearances.count() > 0:
            appearances[0].save() # update the timestamp
        else:
            new_appearance = Appearance()
            new_appearance.room = room
            new_appearance.person = request.user.get_profile()
            new_appearance.save()

            # join message
            m = ChatMessage()
            m.room=room
            m.type=JOIN
            m.author=request.user.get_profile()
            m.save()

    return json_response(data)

def ajax_say(request):
    room_id = request.POST.get('room', 0)
    try:
        room_id = int(room_id)
    except:
        room_id = 0
    room = get_object_or_404(ChatRoom, id=room_id)

    if not chatroom_is_active(room):
        return json_response({})

    data = {
        'user': {
            'is_authenticated': request.user.is_authenticated(),
            'has_permission': False,
        },
    }

    message = request.POST.get('message', '')

    if message == "" or not request.user.is_authenticated():
        return json_response(data)

    data['user']['has_permission'] = user_can_chat(room, request.user)
    if not data['user']['has_permission']:
        return json_response(data)

    # we're clear. add the message
    m = ChatMessage()
    m.room = room
    m.type = MESSAGE
    m.author = request.user.get_profile()
    m.message = message
    m.save()

    return json_response(data)

def chatroom_is_active(room):
    now = datetime.now()
    if not room.start_date is None:
        if room.start_date > now:
            return False
    if not room.end_date is None:
        if room.end_date < now:
            return False
    return True

def ajax_onliners(request):
    room_id = request.GET.get('room', 0)
    try:
        room_id = int(room_id)
    except:
        room_id = 0
    room = get_object_or_404(ChatRoom, id=room_id)

    if not chatroom_is_active(room):
        return json_response({})

    expire_date = datetime.now() - timedelta(seconds=CHAT_TIMEOUT)
    data = [x.person.user.username for x in Appearance.objects.filter(room=room, timestamp__gt=expire_date)]

    return json_response(data)

def user_register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            # create the user
            user = User.objects.create_user(form.cleaned_data.get('username'),
                form.cleaned_data.get('email'),
                form.cleaned_data.get('password'))
            user.save()

            # create a profile
            profile = Profile()
            profile.user = user
            profile.artist_name = form.cleaned_data.get('artist_name')
            profile.activated = False
            profile.activate_code = create_hash(32)
            profile.logon_count = 0
            profile.save()

            # send an activation email
            subject = "Account Confirmation - SolidComposer"
            message = get_template('activation_email.txt').render(Context({ 'username': user.username, 'code': profile.activate_code}))
            from_email = 'admin@solidcomposer.com'
            to_email = user.email
            send_mail(subject, message, from_email, [to_email], fail_silently=True)

            return HttpResponseRedirect("/register/pending/")
    else:
        form = RegisterForm()
    return render_to_response('register.html', {'form': form}, context_instance=RequestContext(request))

def create_hash(length):
    """
    returns a string of length length with random alphanumeric characters
    """
    chars = string.letters + string.digits
    code = ""
    for i in range(length):
        code += chars[random.randint(0, len(chars)-1)]
    return code

def confirm(request, username, code):
    try:
        user = User.objects.get(username=username)
    except:
        err_msg = "Invalid username. Your account may have expired. You can try registering again."
        return render_to_response('confirm_failure.html', locals(), context_instance=RequestContext(request))

    profile = user.get_profile()
    real_code = profile.activate_code

    if real_code == code:
        # activate the account
        user.is_active = True
        user.save()
        profile.activated = True
        profile.save()
        return render_to_response('confirm_success.html', locals(), context_instance=RequestContext(request))
    else:
        err_msg = "Invalid activation code. Nice try!"
        return render_to_response('confirm_failure.html', locals(), context_instance=RequestContext(request))
