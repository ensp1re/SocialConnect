from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
import os
from models import db, bcrypt, User, Post, Message, Conversation
from forms import RegistrationForm, LoginForm, UpdateProfileForm, ChangePasswordForm, SearchForm
from flask_login import LoginManager


app = Flask(__name__)
app.config.from_object('config.Config')
db.init_app(app)
migrate = Migrate(app, db)
bcrypt.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        avatar_file = form.avatar.data
        if avatar_file:
            avatar_filename = secure_filename(avatar_file.filename)
            avatar_path = os.path.join(app.root_path, 'static/uploads', avatar_filename)
            avatar_file.save(avatar_path)
        else:
            avatar_filename = 'default.jpg'

        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_pw, avatar=avatar_filename)
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            response = {'success': True, 'redirect_url': next_page if next_page else url_for('home')}
            return jsonify(response)
        else:
            response = {'success': False, 'message': 'Login Unsuccessful. Please check email and password.'}
            return jsonify(response)

    return render_template('login.html', title='Login', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/profile/<int:user_id>')
@login_required
def profile(user_id):
    user = User.query.get_or_404(user_id)
    is_following = current_user.is_authenticated and current_user.is_following(user)
    return render_template('profile.html', user=user, is_following=is_following)


@app.route('/create_post', methods=['POST'])
@login_required
def create_post():
    content = request.form.get('content')
    if content:
        post = Post(content=content, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash('Your post has been created!', 'success')
    return redirect(url_for('home'))

@app.route('/get_posts')
def get_posts():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.timestamp.desc()).paginate(page=page, per_page=10)
    return render_template('_posts.html', posts=posts.items)

@app.route('/get_user_posts/<int:user_id>')
def get_user_posts(user_id):
    page = request.args.get('page', 1, type=int)
    user = User.query.get_or_404(user_id)
    posts = user.posts.order_by(Post.timestamp.desc()).paginate(page=page, per_page=10)
    return render_template('_posts.html', posts=posts.items)

@app.route('/toggle_follow', methods=['POST'])
@login_required
def toggle_follow():
    user_id = request.form.get('user_id', type=int)
    user = User.query.get_or_404(user_id)
    if current_user.is_following(user):
        current_user.unfollow(user)
        action = 'unfollow'
    else:
        current_user.follow(user)
        action = 'follow'
    db.session.commit()
    return jsonify({
        'success': True,
        'action': action,
        'followers_count': user.followers.count()
    })

@app.route('/messages')
@login_required
def messages():
    conversations = Conversation.query.filter(
        (Conversation.user1 == current_user) | (Conversation.user2 == current_user)
    ).order_by(Conversation.last_message_time.desc()).all()
    
    
    return render_template('messages.html', conversations=conversations)

@app.route('/get_messages/<int:conversation_id>')
@login_required
def get_messages(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)
    
    if current_user not in [conversation.user1, conversation.user2]:
        return jsonify({'error': 'Unauthorized'}), 403
    
    messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.timestamp.asc()).all()
        
    messages_data = [
    {
        'id': message.id,
        'sender_id': message.sender_id,
        'sender_username': message.sender.username,
        'profile_url': url_for('profile', user_id=message.sender_id),  # Generate the profile URL
        'content': message.content,
        'timestamp': message.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
    }
        for message in messages
    ]
    
    
    
    return jsonify({
        'messages': messages_data,
        'conversation_id': conversation_id,
    })

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()

    conversation_id = data.get('conversation_id')
    content = data.get('content')
    
    if conversation_id:
        conversation = Conversation.query.get_or_404(conversation_id)
        if current_user not in [conversation.user1, conversation.user2]:
            return jsonify({'error': 'Unauthorized'}), 403
    else:
        recipient_id = data.get('recipient_id')
        recipient = User.query.get_or_404(recipient_id)
        conversation = Conversation.query.filter(
            ((Conversation.user1 == current_user) & (Conversation.user2 == recipient)) |
            ((Conversation.user1 == recipient) & (Conversation.user2 == current_user))
        ).first()
        if not conversation:
            conversation = Conversation(user1=current_user, user2=recipient)
            db.session.add(conversation)
    
    message = Message(sender_id=current_user.id, conversation_id=conversation.id, content=content)
    db.session.add(message)
    conversation.last_message_time = message.timestamp
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': render_template('_message.html', message=message)
    })



@app.route('/start_conversation/<int:user_id>', methods=['POST'])
@login_required
def start_conversation(user_id):
    recipient = User.query.get_or_404(user_id)
    conversation = Conversation.query.filter(
        ((Conversation.user1 == current_user) & (Conversation.user2 == recipient)) |
        ((Conversation.user1 == recipient) & (Conversation.user2 == current_user))
    ).first()
    
    if not conversation:
        conversation = Conversation(user1=current_user, user2=recipient)
        db.session.add(conversation)
        db.session.commit()
    
    return jsonify({
        'success': True,
        'conversation_id': conversation.id
    })

@app.route('/search', methods=['GET', 'POST'])
def search():
    form = SearchForm()
    if request.method == 'POST':
        query = request.form.get('query')
        users = User.query.filter(User.username.ilike(f'%{query}%')).all()
        posts = Post.query.filter(Post.content.ilike(f'%{query}%')).all()
        return jsonify({
            'users': render_template('_user_results.html', users=users),
            'posts': render_template('_post_results.html', posts=posts)
        })
    return render_template('search.html', form=form)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    profile_form = UpdateProfileForm()
    password_form = ChangePasswordForm()
    
    if request.method == 'POST':
        if 'update_profile' in request.form:
            if profile_form.validate_on_submit():
                if profile_form.avatar.data:
                    avatar_file = profile_form.avatar.data
                    avatar_filename = secure_filename(avatar_file.filename)
                    avatar_path = os.path.join(app.root_path, 'static/uploads', avatar_filename)
                    avatar_file.save(avatar_path)
                    current_user.avatar = avatar_filename
                
                current_user.username = profile_form.username.data
                current_user.bio = profile_form.bio.data
                db.session.commit()
                flash('Your profile has been updated!', 'success')
                return redirect(url_for('settings'))
        
        elif 'change_password' in request.form:
            if password_form.validate_on_submit():
                if bcrypt.check_password_hash(current_user.password, password_form.current_password.data):
                    hashed_password = bcrypt.generate_password_hash(password_form.new_password.data).decode('utf-8')
                    current_user.password = hashed_password
                    db.session.commit()
                    flash('Your password has been updated!', 'success')
                    return redirect(url_for('settings'))
                else:
                    flash('Current password is incorrect.', 'danger')
    
    return render_template('settings.html', profile_form=profile_form, password_form=password_form)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    form = UpdateProfileForm()
    if form.validate_on_submit():
        if form.avatar.data:
            avatar_file = form.avatar.data
            avatar_filename = secure_filename(avatar_file.filename)
            avatar_path = os.path.join(app.root_path, 'static/uploads', avatar_filename)
            avatar_file.save(avatar_path)
            current_user.avatar = avatar_filename
        
        current_user.username = form.username.data
        current_user.bio = form.bio.data
        db.session.commit()
        return jsonify({'success': True, 'message': 'Profile updated successfully!'})
    return jsonify({'success': False, 'message': 'Error updating profile.'})

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if bcrypt.check_password_hash(current_user.password, form.current_password.data):
            hashed_password = bcrypt.generate_password_hash(form.new_password.data).decode('utf-8')
            current_user.password = hashed_password
            db.session.commit()
            return jsonify({'success': True, 'message': 'Password changed successfully!'})
        else:
            return jsonify({'success': False, 'message': 'Current password is incorrect.'})
    return jsonify({'success': False, 'message': 'Error changing password.'})

if __name__ == '__main__':
    app.run(debug=True)