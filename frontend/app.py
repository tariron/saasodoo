from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html', message='Welcome to the Frontend!')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/buy')
def buy():
    return render_template('buy.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 