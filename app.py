from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_from_directory,
    abort,
    render_template_string,
    jsonify,
)
import json, os, html, logging, shutil
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.utils import safe_join
from dotenv import load_dotenv
from functools import wraps 

app = Flask(__name__)

load_dotenv()  # 加载.env文件
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    # 生成安全的随机密钥
    app.secret_key = os.urandom(24).hex()
    app.logger.warning(
        "Using auto-generated secret key. Set SECRET_KEY in .env for production."
    )

user_home = os.path.expanduser("~")
print(user_home)
BASE_DIR = user_home


def secure_path_join(base_path, user_path):
    """安全的路径拼接函数"""
    try:
        # 规范化路径，移除多余的..
        safe_path = os.path.normpath(user_path)
        # 确保路径仍在base_dir内
        full_path = safe_join(base_path, safe_path.lstrip("/"))

        # 再次验证路径在base_dir内
        if not full_path.startswith(os.path.abspath(base_path)):
            app.logger.warning(f"Path traversal attempt: {user_path}")
            abort(403)

        return full_path
    except Exception as e:
        app.logger.error(f"Path validation error: {e}")
        abort(400)


# 清除现有的Handlers
app.logger.handlers = []

# 创建并添加新的Handler
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s][%(filename)s:%(lineno)d:%(funcName)s] %(message)s"
)
handler.setFormatter(formatter)
app.logger.addHandler(handler)

# 设置日志级别
app.logger.setLevel(logging.INFO)

# 配置
UPLOAD_FOLDER = BASE_DIR  # 修改为您的上传目录
ALLOWED_EXTENSIONS = {
    "txt",
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "zip",
    "tar",
    "gz",
    "7z",
}
MAX_CONTENT_LENGTH = 6 * 1024 * 1024 * 1024  # 6GB最大文件大小

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def load_users():
    if os.path.exists("users.json"):
        with open("users.json") as f:
            return json.load(f)
    return {}


def save_users(users):
    with open("users.json", "w") as f:
        json.dump(users, f)


users = load_users()


# entry
@app.route("/", defaults={"url_path": "/"}, methods=["GET"])
@app.route("/<path:url_path>", methods=["GET"])
def web_entry(url_path):
    if "username" in session:
        app.logger.info(f"web_entry, url:{url_path}")
        action = request.args.get("action")
        filename = secure_path_join(BASE_DIR, url_path)
        if os.path.exists(filename):
            if action == "download":
                return download_file(filename)
            elif action == "preview":
                return file_preview(filename)
            else:
                if os.path.isdir(filename):
                    return render_template("browser.html")
                elif os.path.isfile(filename):
                    return file_preview(filename)
                else:
                    return jsonify({"error": "Invalid action"}), 400
        else:
            app.logger.error(f"web_entry, file not found:{filename}")
            return jsonify({"error": "file is not exist"}), 400
    return redirect(url_for("login"))


# 构建响应数据
@app.route("/", defaults={"file_path": "/"}, methods=["PUT"])
@app.route("/<path:file_path>", methods=["PUT"])
def data_response_put_api(file_path):
    if "username" not in session:
        app.logger.error(f"Not login")
        return jsonify({"directories": [], "files": []}), 401
    # 使用安全的路径处理
    app.logger.info(f"=== data request url: {file_path}")
    try:
        dir_path = secure_path_join(BASE_DIR, file_path)
    except:
        return jsonify({"directories": [], "files": []}), 403

    if not os.path.isdir(dir_path):
        app.logger.info(f"dir is not exist:{dir_path}")
        return jsonify({"directories": [], "files": []}), 404

    # 初始化目录和文件列表
    directories = []
    files = []
    # 遍历目录内容
    for entry in os.scandir(dir_path):
        if entry.name.startswith("."):
            continue
        modify_time = datetime.utcfromtimestamp(entry.stat().st_mtime).isoformat()
        file_info = {
            "key": entry.name,
            "size": entry.stat().st_size,
            "lastModified": modify_time,
        }
        if entry.is_dir():
            directories.append(file_info)
        elif entry.is_file():
            files.append(file_info)
    response_data = {
        "directories": directories,
        "files": files,
    }
    return jsonify(response_data)


def delete_directory(path):
    try:
        shutil.rmtree(path)
        app.logger.info(f"Successfully deleted the directory: {path}")
    except Exception as e:
        app.logger.info(f"Error: {e}")


import shutil
from datetime import datetime

# 添加回收站功能
TRASH_DIR = os.path.join(BASE_DIR, ".trash")
os.makedirs(TRASH_DIR, exist_ok=True)


def move_to_trash(filepath):
    """移动文件到回收站而不是直接删除"""
    if not os.path.exists(filepath):
        return False
    try:
        # 生成唯一的回收站路径
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        basename = os.path.basename(filepath)
        trash_path = os.path.join(TRASH_DIR, f"{timestamp}_{basename}")

        # 移动文件到回收站
        if os.path.isdir(filepath):
            shutil.move(filepath, trash_path)
        else:
            shutil.move(filepath, trash_path)

        app.logger.info(f"Moved to trash: {filepath} -> {trash_path}")
        return True
    except Exception as e:
        app.logger.error(f"Move to trash failed: {e}")
        return False

# 定义一个需要root权限的装饰器
def root_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            abort(401)
        if session.get('username') != 'root':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# DELETE处理
@app.route("/<path:url_path>", methods=["DELETE"])
@root_required
def delete_route_api(url_path):
    if "username" not in session:
        abort(401)

    # 1. 路径安全验证
    filename = secure_path_join(BASE_DIR, url_path)
    app.logger.info(f"DELETE request for: {filename}")
    # 2. 验证用户权限（示例：只允许admin删除）
    if session.get("username") != "root":
        abort(403)

    # 3. 验证文件存在
    if not os.path.exists(filename):
        abort(404)

    # 4. 移动到回收站而不是直接删除
    if move_to_trash(filename):
        return jsonify({"success": True, "message": "文件已移至回收站"}), 200
    else:
        return jsonify({"error": "删除失败"}), 500


suffix_lang = {
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cpp": "cpp",
    ".sh": "bash",
    ".py": "python",
    ".md": "markdown",
}


def file_preview(filename, max_size=10 * 1024 * 1024):
    if "username" in session:
        if os.path.isfile(filename):
            # 检查文件大小
            file_size = os.path.getsize(filename)
            if file_size > max_size:
                app.logger.info(f"File size {file_size} exceed max size {max_size}")
                return send_from_directory(
                    os.path.dirname(filename), os.path.basename(filename)
                )
            suffix = os.path.splitext(filename)[1]
            if suffix in suffix_lang:
                try:
                    with open(filename, "r") as file:
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
                return send_from_directory(
                    os.path.dirname(filename), os.path.basename(filename)
                )
        else:
            app.logger.error(f"Preview: Not found: {filename}")
            abort(404)
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = users.get(username)
        if user and check_password_hash(user["password"], password):
            session["username"] = username
            # return render_template('browser.html')
            return redirect(url_for("web_entry", url_path="/"))
        else:
            return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")


@app.route("/welcome")
def welcome():
    if "username" in session:
        return render_template(
            "welcome.html", message=f"Welcome, {session['username']}!"
        )
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("login"))


@app.route("/add_user", methods=["GET", "POST"])
def add_user():
    if "username" in session and session["username"] == "root":
        if request.method == "POST":
            new_username = request.form["username"]
            new_password = request.form["password"]
            if new_username in users:
                return "User already exists"
            users[new_username] = {"password": generate_password_hash(new_password)}
            save_users(users)
            return f"User {new_username} added successfully"
        return render_template("add_user.html")
    return redirect(url_for("login"))


@app.route("/file_browser")
def file_browser():
    if "username" in session:
        try:
            path = BASE_DIR
            print("/file_browser, path:", path)
            items = [
                {"name": item, "is_dir": os.path.isdir(secure_path_join(path, item))}
                for item in os.listdir(path)
            ]
        except FileNotFoundError:
            items = []
        return render_template("file_browser.html", items=items, curr_path=path)
    return redirect(url_for("login"))


@app.route("/download/<filename>")
def download_file(filename):
    if "username" not in session:
        abort(401)
    file_path = secure_path_join(BASE_DIR, filename)
    app.logger.info(f"download_file:{file_path}")

    if os.path.isfile(file_path):
        app.logger.info(f"do download file:{file_path}")
        return send_from_directory(
            os.path.dirname(file_path), os.path.basename(file_path), as_attachment=True
        )
    else:
        app.logger.error(f"Not found file:{file_path}")
        abort(404)
    return redirect(url_for("login"))


# 检查文件扩展名
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# 确保目录存在
def ensure_directory_exists(path):
    if not os.path.exists(path):
        os.makedirs(path)


# 文件上传路由
@app.route("/upload", methods=["POST"])
def upload_file():
    # 检查是否有文件部分
    if "file" not in request.files:
        return jsonify({"error": "没有文件部分"}), 400

    file = request.files["file"]
    path = request.form.get("path", "/")

    app.logger.info(f"path:{path}")
    # 如果用户没有选择文件
    if file.filename == "":
        return jsonify({"error": "没有选择文件"}), 400

    if file and allowed_file(file.filename):
        # 安全处理文件名
        filename = secure_filename(file.filename)

        # 构建完整路径

        target_path = secure_path_join(app.config["UPLOAD_FOLDER"], path.lstrip("/"))
        ensure_directory_exists(target_path)

        # 完整文件路径
        filepath = secure_path_join(target_path, filename)

        try:
            # 保存文件
            file.save(filepath)

            # 获取文件信息
            file_size = os.path.getsize(filepath)

            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"文件 {filename} 上传成功",
                        "filename": filename,
                        "size": file_size,
                        "path": path,
                    }
                ),
                200,
            )

        except Exception as e:
            return jsonify({"error": f"保存文件时出错: {str(e)}"}), 500

    return jsonify({"error": "不允许的文件类型"}), 400


# 批量上传
@app.route("/upload/batch", methods=["POST"])
def upload_batch():
    files = request.files.getlist("files[]")
    path = request.form.get("path", "/")

    if not files:
        return jsonify({"error": "没有文件"}), 400

    results = []
    target_path = secure_path_join(app.config["UPLOAD_FOLDER"], path.lstrip("/"))
    ensure_directory_exists(target_path)

    for file in files:
        if file.filename == "":
            continue

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = secure_path_join(target_path, filename)

            try:
                file.save(filepath)
                results.append(
                    {"filename": filename, "success": True, "message": "上传成功"}
                )
            except Exception as e:
                results.append(
                    {
                        "filename": filename,
                        "success": False,
                        "message": f"上传失败: {str(e)}",
                    }
                )
        else:
            results.append(
                {
                    "filename": file.filename,
                    "success": False,
                    "message": "不允许的文件类型",
                }
            )

    return (
        jsonify(
            {
                "total": len(files),
                "successful": len([r for r in results if r["success"]]),
                "failed": len([r for r in results if not r["success"]]),
                "results": results,
            }
        ),
        200,
    )


# 添加在您的Flask路由中
@app.route("/api/userinfo", methods=["GET"])
def get_userinfo():
    if "username" in session:
        return jsonify({"username": session["username"], "loggedIn": True})
    return jsonify({"username": None, "loggedIn": False}), 401


# 获取上传进度（可选，用于更精确的进度控制）
@app.route("/upload/progress", methods=["GET"])
def upload_progress():
    # 这里可以实现基于session或临时文件的进度查询
    # 需要更复杂的实现来跟踪每个上传的进度
    return jsonify({"progress": 0}), 200


app.config.update(
    SESSION_COOKIE_SECURE=False,  # 生产环境应该为True
    SESSION_COOKIE_HTTPONLY=True,  # 应该启用
    SESSION_COOKIE_SAMESITE="Lax",  # 推荐Lax
    PERMANENT_SESSION_LIFETIME=36000,  # 10小时过期
)
if __name__ == "__main__":
    app.logger.info(f"run")
    app.run(host="0.0.0.0", port=5000, debug=True)
