from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

# Initialize the Flask app and configure the database URI
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://astrolog:astrolog1414@localhost/astrolog' # Path to the database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Models for the database tables
class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    birthdate = db.Column(db.String(10))
    gender = db.Column(db.String(10))
    zodiac = db.Column(db.String(20))
    chinese_year = db.Column(db.String(20))

class QuestionChain(db.Model):
    __tablename__ = 'question_chains'
    id = db.Column(db.Integer, primary_key=True)
    chain_id = db.Column(db.Integer, unique=True, nullable=False)
    chain_name = db.Column(db.String(100), nullable=False)
    question = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    key = db.Column(db.String(50), nullable=False)
    options = db.Column(db.Text, nullable=True)
    chain_order = db.Column(db.Integer, nullable=False)
    options_position = db.Column(db.String(100), nullable=True)  # ← ДОБАВЛЕНО

class DynamicMenu(db.Model):
    __tablename__ = 'dynamic_menu'
    id = db.Column(db.Integer, primary_key=True)
    button_name = db.Column(db.String(100), nullable=False)
    button_action = db.Column(db.String(100), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    chain_id = db.Column(db.Integer, db.ForeignKey('question_chains.chain_id'), nullable=True)
    menu_chain_id = db.Column(db.Integer, nullable=True)  # Новое поле

class QuestionChainPrompt(db.Model):
    __tablename__ = 'question_chain_prompts'
    chain_p_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    chain_id = db.Column(db.Integer, db.ForeignKey('question_chains.chain_id'), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    tone = db.Column(db.String(50), nullable=True)
    temperature = db.Column(db.Float, nullable=True)
    chain_order = db.Column(db.Integer, nullable=False)

    # Связь с цепочкой вопросов
    chain = db.relationship('QuestionChain', backref=db.backref('prompts', lazy=True))


# Routes for the app

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manage_users')
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if request.method == 'POST':
        options_position = request.form.get('options_position')
        name = request.form['name']
        birthdate = request.form['birthdate']
        gender = request.form['gender']
        zodiac = request.form['zodiac']
        chinese_year = request.form['chinese_year']
        
        new_user = User(name=name, birthdate=birthdate, gender=gender, zodiac=zodiac, chinese_year=chinese_year)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('add_user.html')

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    user = User.query.get(user_id)
    if request.method == 'POST':
        options_position = request.form.get('options_position')
        user.name = request.form['name']
        user.birthdate = request.form['birthdate']
        user.gender = request.form['gender']
        user.zodiac = request.form['zodiac']
        user.chinese_year = request.form['chinese_year']
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit_user.html', user=user)

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    user = User.query.get(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/add_question_chain', methods=['GET', 'POST'])
def add_question_chain():
    if request.method == 'POST':
        options_position = request.form.get('options_position')
        chain_id = request.form['chain_id']
        chain_name = request.form['chain_name']
        question = request.form['question']
        q_type = request.form['type']
        key = request.form['key']
        options = request.form.get('options', '')
        chain_order = request.form['chain_order']
        options_position = request.form.get('options_position')

        new_chain = QuestionChain(
            chain_id=chain_id, 
            chain_name=chain_name, 
            question=question, 
            type=q_type, 
            key=key, 
            options=options, 
            chain_order=chain_order
        )
        db.session.add(new_chain)
        db.session.commit()
        return redirect(url_for('manage_question_chains'))
    return render_template('add_question_chain.html')

@app.route('/manage_question_chains')
def manage_question_chains():
    chains = QuestionChain.query.order_by(QuestionChain.chain_id, QuestionChain.chain_order).all()
    grouped_chains = {}
    for chain in chains:
        if chain.chain_id not in grouped_chains:
            grouped_chains[chain.chain_id] = []
        grouped_chains[chain.chain_id].append(chain)
    return render_template('manage_question_chains.html', grouped_chains=grouped_chains)

@app.route('/edit_question_chain/<int:chain_id>', methods=['GET', 'POST'])
def edit_question_chain(chain_id):
    # Получаем цепочку по chain_id
    chain = QuestionChain.query.filter_by(chain_id=chain_id).all()
    
    # Получаем все вопросы, связанные с этой цепочкой, сортировка по chain_order
    questions = QuestionChain.query.filter_by(chain_id=chain_id).order_by(QuestionChain.chain_order).all()

    # Если это POST запрос, обрабатываем редактирование всех вопросов в цепочке
    if request.method == 'POST':
        options_position = request.form.get('options_position')
        for question in questions:
            question.chain_name = request.form.get(f'chain_name_{question.id}')
            question.question = request.form.get(f'question_{question.id}')
            question.type = request.form.get(f'type_{question.id}')
            question.key = request.form.get(f'key_{question.id}')
            question.options = request.form.get(f'options_{question.id}')
            question.chain_order = request.form.get(f'chain_order_{question.id}')
            question.options_position = request.form.get(f'options_position_{question.id}')
        db.session.commit()
        return redirect(url_for('edit_question_chain', chain_id=chain_id))

    return render_template('edit_question_chain.html', chain=chain, questions=questions, chain_id=chain_id)


@app.route('/delete_question_chain/<int:id>')
def delete_question_chain(id):
    chain = QuestionChain.query.get(id)
    db.session.delete(chain)
    db.session.commit()
    return redirect(url_for('manage_question_chains'))

@app.route('/add_dynamic_menu', methods=['GET', 'POST'])
def add_dynamic_menu():
    if request.method == 'POST':
        options_position = request.form.get('options_position')
        button_name = request.form['button_name']
        button_action = request.form['button_action']
        position = request.form['position']
        chain_id = request.form['chain_id']
        menu_chain_id = request.form.get('menu_chain_id')

        new_menu_button = DynamicMenu(
            button_name=button_name,
            button_action=button_action,
            position=position,
            chain_id=chain_id,
            menu_chain_id=menu_chain_id
        )
        db.session.add(new_menu_button)
        db.session.commit()
        return redirect(url_for('manage_dynamic_menu'))
    return render_template('add_dynamic_menu.html')

@app.route('/manage_dynamic_menu')
def manage_dynamic_menu():
    menu_buttons = DynamicMenu.query.all()
    return render_template('manage_dynamic_menu.html', menu_buttons=menu_buttons)

@app.route('/edit_dynamic_menu/<int:menu_id>', methods=['GET', 'POST'])
def edit_dynamic_menu(menu_id):
    menu_button = DynamicMenu.query.get(menu_id)
    if request.method == 'POST':
        options_position = request.form.get('options_position')
        menu_button.button_name = request.form['button_name']
        menu_button.button_action = request.form['button_action']
        menu_button.position = request.form['position']
        menu_button.chain_id = request.form['chain_id']
        menu_button.menu_chain_id = request.form.get('menu_chain_id')
        db.session.commit()
        return redirect(url_for('manage_dynamic_menu'))
    return render_template('edit_dynamic_menu.html', menu_button=menu_button)

@app.route('/delete_dynamic_menu/<int:menu_id>')
def delete_dynamic_menu(menu_id):
    menu_button = DynamicMenu.query.get(menu_id)
    db.session.delete(menu_button)
    db.session.commit()
    return redirect(url_for('manage_dynamic_menu'))

@app.route('/add_question_to_chain/<int:chain_id>', methods=['GET', 'POST'])
def add_question_to_chain(chain_id):
    # Получаем информацию о цепочке
    chain = QuestionChain.query.filter_by(chain_id=chain_id).first()

    # Находим максимальный chain_order для этой цепочки
    max_chain_order = db.session.query(db.func.max(QuestionChain.chain_order)).filter_by(chain_id=chain_id).scalar() or 0

    if request.method == 'POST':
        options_position = request.form.get('options_position')
        # Создаем новый вопрос с предзаполненными значениями
        new_question = QuestionChain(
            chain_id=chain_id,
            chain_name=chain.chain_name,
            question=request.form['question'],
            type=request.form['type'],
            key=request.form['key'],
            options=request.form['options'],
            chain_order=max_chain_order + 1
        )
        db.session.add(new_question)
        db.session.commit()
        return redirect(url_for('edit_question_chain', chain_id=chain_id))

    return render_template('add_question_to_chain.html', chain=chain, max_chain_order=max_chain_order)

@app.route('/edit_question/<int:question_id>', methods=['GET', 'POST'])
def edit_question(question_id):
    # Получаем вопрос по id
    question = QuestionChain.query.get_or_404(question_id)
    
    if request.method == 'POST':
        options_position = request.form.get('options_position')
        # Обрабатываем редактирование вопроса
        question.question = request.form['question']
        question.type = request.form['type']
        question.key = request.form['key']
        question.options = request.form['options']
        question.chain_order = request.form['chain_order']
        question.options_position = request.form['options_position']
        options_position = request.form.get('options_position')
        
        db.session.commit()
        return redirect(url_for('edit_question_chain', chain_id=question.chain_id))

    # Отправляем вопрос в шаблон для редактирования
    return render_template('edit_question.html', question=question)

@app.route('/delete_question/<int:question_id>', methods=['GET', 'POST'])
def delete_question(question_id):
    question = QuestionChain.query.get_or_404(question_id)
    chain_id = question.chain_id
    db.session.delete(question)
    db.session.commit()
    return redirect(url_for('edit_question_chain', chain_id=chain_id))

@app.route('/add_prompt_to_chain/<int:chain_id>', methods=['GET', 'POST'])
def add_prompt_to_chain(chain_id):
    # Получаем информацию о цепочке
    chain = QuestionChain.query.filter_by(chain_id=chain_id).first()

    # Находим максимальный chain_order для этой цепочки в таблице question_chain_prompts
    max_chain_order = db.session.query(db.func.max(QuestionChainPrompt.chain_order)).filter_by(chain_id=chain_id).scalar() or 0

    if request.method == 'POST':
        options_position = request.form.get('options_position')
        # Создаем новый промт с предзаполненными значениями
        new_prompt = QuestionChainPrompt(
            chain_id=chain_id,
            prompt=request.form['prompt'],
            tone=request.form['tone'],
            temperature=request.form['temperature'],
            chain_order=max_chain_order + 1
        )
        db.session.add(new_prompt)
        db.session.commit()
        return redirect(url_for('edit_question_chain', chain_id=chain_id))

    return render_template('add_prompt_to_chain.html', chain=chain, max_chain_order=max_chain_order)



@app.route('/edit_prompt/<int:chain_p_id>', methods=['GET', 'POST'])
def edit_prompt(chain_p_id):
    # Получаем нужный промт по chain_p_id
    prompt = QuestionChainPrompt.query.get_or_404(chain_p_id)

    if request.method == 'POST':
        options_position = request.form.get('options_position')
        # Обрабатываем редактирование промта
        prompt.prompt = request.form['prompt']
        prompt.tone = request.form['tone']
        prompt.temperature = request.form['temperature']
        prompt.chain_order = request.form['chain_order']
        options_position = request.form.get('options_position')

        db.session.commit()
        return redirect(url_for('edit_question_chain', chain_id=prompt.chain_id))

    # Отправляем промт в шаблон для редактирования
    return render_template('edit_prompt.html', prompt=prompt)

@app.route('/delete_prompt/<int:chain_p_id>', methods=['GET', 'POST'])
def delete_prompt(chain_p_id):
    prompt = QuestionChainPrompt.query.get_or_404(chain_p_id)
    chain_id = prompt.chain_id
    db.session.delete(prompt)
    db.session.commit()
    return redirect(url_for('edit_question_chain', chain_id=chain_id))



if __name__ == '__main__':
    app.run(debug=True)
