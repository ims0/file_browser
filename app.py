from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, abort, render_template_string,jsonify
import json, os, html, logging
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 请替换为你自己的密钥
BASE_DIR = '/home/ubuntu/'


# 清除现有的Handlers
app.logger.handlers = []

# 创建并添加新的Handler
handler = logging.StreamHandler()
formatter = logging.Formatter( '%(asctime)s [%(levelname)s][%(filename)s:%(lineno)d:%(funcName)s]%(message)s')
handler.setFormatter(formatter)
app.logger.addHandler(handler)

# 设置日志级别
app.logger.setLevel(logging.INFO)

def load_users():
    if os.path.exists('users.json'):
        with open('users.json') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(users, f)

users = load_users()

# entry
@app.route('/', defaults={'url_path': '/'}, methods=['GET'])
@app.route('/<path:url_path>', methods=['GET'])
def web_entry(url_path):
    if 'username' in session:
        app.logger.info(f'web_entry, url:{url_path}')
        action = request.args.get('action')
        filename = os.path.join(BASE_DIR, url_path)
        if os.path.exists(filename):
            if action == 'download':
                return download_file(filename)
            elif action == 'preview':
                return file_preview(filename)
            else:
                if os.path.isdir(filename) :
                    return render_template('file.html')
                elif os.path.isfile(filename):
                    return file_preview(filename)
                else :
                    return jsonify({"error": "Invalid action"}), 400
        else :
            app.logger.error(f'web_entry, file not found:{filename}')
            return jsonify({"error": "file is not exist"}), 400
    return redirect(url_for('login'))

# 构建响应数据
@app.route('/', defaults={'file_path': '/'}, methods=['PUT'])
@app.route('/<path:file_path>', methods=['PUT'])
def data_response_put_api(file_path):
    app.logger.info(f'=== data request url: {file_path}')
    response_data = {
        "directories": [],
        "files": [],
    }
    if 'username' not in session:
        print("file_response, file_path arg:", file_path)
        app.logger.info(f'Not login')
        return jsonify(response_data)
    # 指定要列出的目录路径
    if file_path[0] != '/' :
        file_path = '/' + file_path

    dir_path = BASE_DIR + file_path

    if not os.path.isdir(dir_path):
        app.logger.info(f"dir is not exist:{dir_path}")
        return jsonify(response_data)

    # 初始化目录和文件列表
    directories = []
    files = []
    # 遍历目录内容
    for entry in os.scandir(dir_path):
        #print(entry.path, ":", entry.path.removeprefix(BASE_DIR), "basedir:",BASE_DIR )
        base_name = os.path.basename(entry.path)
        if base_name.startswith('.'):
            continue
        if entry.is_dir():
            directories.append(base_name)
        elif entry.is_file():
            # 获取文件信息
            file_info = {
                "key": base_name,
                "size": entry.stat().st_size,
                "lastModified": datetime.utcfromtimestamp(entry.stat().st_mtime).isoformat() + 'Z'
            }
            files.append(file_info)

    # 构建响应数据
    response_data = {
        "directories": directories,
        "files": files,
    }
    return jsonify(response_data)

# DELETE
@app.route('/<path:url_path>', methods=['DELETE'])
def delete_route_api(url_path):
    app.logger.info(f'url:{url_path}')
    if 'username' in session:
        filename = os.path.join(BASE_DIR, url_path)
        if os.path.exists(filename):
            os.remove(filename)
            app.logger.warning(f'Delete: {filename} finish!')
            return render_template('file.html')
        else:
            app.logger.error(f'Not found:{url_path}')
            return render_template('file.html')
    else:
        return redirect(url_for('login'))

suffix_lang = {'.c': 'c', '.h': 'c', '.hpp':'cpp', '.cpp':'cpp', '.sh':'bash', '.py':'python'}
def file_preview( filename):
    if 'username' in session:
        if os.path.isdir(filename):
            items = [{'name': item, 'is_dir': os.path.isdir(filename+'/' + item)} for item in os.listdir(filename)]
            return render_template('file_browser.html', items=items, curr_path=filename)
        elif os.path.isfile(filename):
            suffix = os.path.splitext(filename)[1]
            if suffix in suffix_lang:
                try:
                   with open(filename, 'r') as file:
                       content = file.read()
                       escaped_content = html.escape(content)  # 这里进行转义处理
                   # 使用模板字符串渲染 HTML
                   html_content = f"""
                   <!DOCTYPE html>
                   <html lang="en">
                   <head>
                       <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/styles/default.min.css">
                       <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/highlight.min.js"></script>
                       <script>hljs.highlightAll();</script>
                   </head>
                   <body> <pre><code class="language-{suffix_lang[suffix]}">{escaped_content}</code></pre> </body>
                   </html>
                   """
                   print("preview:", filename)
                   return render_template_string(html_content)
                except FileNotFoundError:
                   return "File not found", 404
            else:
                return send_from_directory(os.path.dirname(filename), os.path.basename(filename))
        else:
            app.logger.error(f'Preview: Not found: {filename}')
            abort(404)
    return redirect(url_for('login'))
#@app.route('/')
#def home():
#    if 'username' in session:
#        return redirect(url_for('welcome'))
#    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users.get(username)
        if user and check_password_hash(user['password'], password):
            session['username'] = username
            return redirect(url_for('welcome'))
        else:
            return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/welcome')
def welcome():
    if 'username' in session:
        return render_template('welcome.html', message=f"Welcome, {session['username']}!")
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if 'username' in session and session['username'] == 'root':
        if request.method == 'POST':
            new_username = request.form['username']
            new_password = request.form['password']
            if new_username in users:
                return "User already exists"
            users[new_username] = {'password': generate_password_hash(new_password)}
            save_users(users)
            return f"User {new_username} added successfully"
        return render_template('add_user.html')
    return redirect(url_for('login'))


@app.route('/file_browser')
def file_browser():
    if 'username' in session:
        try:
            path = BASE_DIR
            print("/file_browser, path:", path)
            items = [{'name': item, 'is_dir': os.path.isdir(os.path.join(path, item))} for item in os.listdir(path)]
        except FileNotFoundError:
            items = []
        return render_template('file_browser.html', items=items, curr_path=path)
    return redirect(url_for('login'))

#@app.route('/file/<filename>')
#def file_preview(filename):
#    if 'username' in session:
#        file_path = os.path.join(BASE_DIR, filename)
#        if os.path.isfile(file_path):
#            return send_from_directory(BASE_DIR, filename)
#        else:
#            abort(404)
#    return redirect(url_for('login'))

@app.route('/download/<filename>')
def download_file(filename):
    if 'username' in session:
        file_path = os.path.join(BASE_DIR, filename)
        app.logger.info(f'file_path:{file_path}')
        if os.path.isfile(file_path):
            app.logger.info(f'do download file:{file_path}')
            return send_from_directory(os.path.dirname(filename), os.path.basename(filename), as_attachment=True)
        else:
            app.logger.error(f'Not found file:{file_path}')
            abort(404)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.logger.info(f'run')
    app.run(host='127.0.0.1', port=5000, debug=True)
