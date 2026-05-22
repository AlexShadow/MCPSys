import subprocess
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import ttkbootstrap as ttkb
from ttkbootstrap.widgets.scrolled import ScrolledText
import httpx
from openai import OpenAI

# Попробуем импортировать anthropic
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# ---------- Определение путей ----------
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BASE_DIR

CONFIG_FILE = os.path.join(APP_DIR, "config.json")
DEFAULT_SIZE = "1280x800"

# ---------- Настройки по умолчанию ----------
DEFAULT_PROVIDER = "deepseek"          # deepseek / openai / anthropic / groq / together / ollama / openrouter / custom
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_KEY = ""
DEFAULT_INPUT_HEIGHT = 80
DEFAULT_SSH_USER = "root"
DEFAULT_SSH_HOST = ""
DEFAULT_SSH_KEY_PATH = os.path.expanduser(r"~/.ssh/id_ed25519")

REMOTE_SERVER_DIR = "/opt/mcp-server"
REMOTE_SERVER_BIN = f"{REMOTE_SERVER_DIR}/mcp-server"
REMOTE_TOOLS_FILE = f"{REMOTE_SERVER_DIR}/tools.toml"
MCP_COMMAND = f"{REMOTE_SERVER_BIN} {REMOTE_TOOLS_FILE}"

# Базовые URL для предустановленных провайдеров
PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "ollama": "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    # custom – пользователь вводит сам
}

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stdin is not None:
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

# ---------- Функции работы с SSH ----------
def copy_ssh_key_to_server(host, user, key_path, password=None):
    if not host or not user:
        messagebox.showerror("Ошибка", "Укажите Host и User.")
        return False
    if not PARAMIKO_AVAILABLE:
        messagebox.showerror("Ошибка", "Библиотека paramiko не установлена.\nУстановите: pip install paramiko")
        return False
    if not os.path.exists(key_path):
        messagebox.showerror("Ошибка", f"Файл ключа не найден:\n{key_path}")
        return False
    pub_key_path = key_path + ".pub"
    if not os.path.exists(pub_key_path):
        messagebox.showerror("Ошибка", f"Публичный ключ не найден:\n{pub_key_path}")
        return False
    try:
        with open(pub_key_path, 'r', encoding='utf-8') as f:
            pub_key = f.read().strip()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось прочитать публичный ключ:\n{e}")
        return False
    if password is None:
        password = simpledialog.askstring("SSH пароль", f"Введите пароль для {user}@{host}:", show='*')
        if not password:
            return False
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=user, password=password, timeout=15)
        command = (
            f'mkdir -p ~/.ssh && '
            f'echo "{pub_key}" >> ~/.ssh/authorized_keys && '
            f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys'
        )
        stdin, stdout, stderr = ssh.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        ssh.close()
        if exit_status == 0:
            messagebox.showinfo("Успех", f"Ключ скопирован на {user}@{host}")
            return True
        else:
            error = stderr.read().decode()
            messagebox.showerror("Ошибка", f"Не удалось добавить ключ:\n{error}")
            return False
    except paramiko.AuthenticationException:
        messagebox.showerror("Ошибка", "Неверный пароль или имя пользователя.")
        return False
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка подключения:\n{e}")
        return False

def check_server_installed(host, user, password):
    if not PARAMIKO_AVAILABLE:
        return "unknown"
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=user, password=password, timeout=10)
        stdin, stdout, stderr = ssh.exec_command(f"test -f {REMOTE_SERVER_BIN} && echo 'yes' || echo 'no'")
        result = stdout.read().decode().strip()
        ssh.close()
        return result == "yes"
    except:
        return False

def install_server_to_debian(host, user, password, key_path, progress_callback=None):
    if not PARAMIKO_AVAILABLE:
        raise RuntimeError("paramiko не установлен")

    local_bin = os.path.join(BASE_DIR, "mcp-server")
    if not os.path.exists(local_bin):
        local_bin = os.path.join(APP_DIR, "mcp-server")
    if not os.path.exists(local_bin):
        raise FileNotFoundError("mcp-server binary not found in package")

    local_tools = os.path.join(BASE_DIR, "tools.toml")
    if not os.path.exists(local_tools):
        local_tools = os.path.join(APP_DIR, "tools.toml")
    if not os.path.exists(local_tools):
        raise FileNotFoundError("tools.toml not found in package")

    pub_key_path = key_path + ".pub"
    if not os.path.exists(pub_key_path):
        raise FileNotFoundError(f"Public key not found: {pub_key_path}")
    with open(pub_key_path, 'r', encoding='utf-8') as f:
        pub_key = f.read().strip()

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=user, password=password, timeout=15)
        sftp = ssh.open_sftp()

        ssh.exec_command(f"mkdir -p {REMOTE_SERVER_DIR}")
        sftp.put(local_bin, REMOTE_SERVER_BIN)
        sftp.chmod(REMOTE_SERVER_BIN, 0o755)
        sftp.put(local_tools, REMOTE_TOOLS_FILE)

        ssh.exec_command(
            f'mkdir -p ~/.ssh && '
            f'echo "{pub_key}" >> ~/.ssh/authorized_keys && '
            f'chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys'
        )

        sftp.close()
        stdin, stdout, stderr = ssh.exec_command(f"test -x {REMOTE_SERVER_BIN} && echo 'ok'")
        result = stdout.read().decode().strip()
        ssh.close()

        if result != "ok":
            raise RuntimeError("Server binary is not executable after upload")

        if progress_callback:
            progress_callback("Server installed and SSH key copied!")
        return True, "Server installed and SSH key copied successfully"
    except Exception as e:
        if progress_callback:
            progress_callback(f"Installation failed: {e}")
        return False, str(e)

# ---------- MCPClient ----------
class MCPClient:
    def __init__(self, ssh_user, ssh_host, command, key_path=None):
        if not ssh_host:
            raise ValueError("SSH host не задан")
        ssh_target = f"{ssh_user}@{ssh_host}" if ssh_user else ssh_host
        ssh_args = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
        if key_path and os.path.exists(key_path):
            ssh_args.extend(["-i", key_path])
        ssh_args.extend([ssh_target, command])

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        else:
            creationflags = 0

        self.process = subprocess.Popen(
            ssh_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            startupinfo=startupinfo,
            creationflags=creationflags
        )
        self.request_id = 0
        self.tools = []
        self._initialize()

    def _send_request(self, method, params=None):
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self.request_id
        }
        req_str = json.dumps(request) + "\n"
        try:
            self.process.stdin.write(req_str)
            self.process.stdin.flush()
        except BrokenPipeError:
            stderr_output = self.process.stderr.read()
            raise Exception(f"Процесс завершился неожиданно. stderr:\n{stderr_output}")

        response_line = self.process.stdout.readline()
        if not response_line:
            stderr_output = self.process.stderr.read()
            raise Exception(f"Нет ответа от MCP сервера. stderr:\n{stderr_output}")
        response = json.loads(response_line)
        if "error" in response:
            raise Exception(f"Ошибка от сервера: {response['error']}")
        return response

    def _send_notification(self, method, params):
        notif = {"jsonrpc": "2.0", "method": method, "params": params}
        self.process.stdin.write(json.dumps(notif) + "\n")
        self.process.stdin.flush()

    def _initialize(self):
        self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "deepseek-gui", "version": "1.0.0"}
        })
        self._send_notification("notifications/initialized", {})
        self._load_tools()

    def _load_tools(self):
        resp = self._send_request("tools/list")
        self.tools = resp.get("result", {}).get("tools", [])

    def call_tool(self, name, arguments):
        resp = self._send_request("tools/call", {"name": name, "arguments": arguments})
        return resp.get("result")

    def close(self):
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)

def convert_tools_for_openai(mcp_tools, disabled_set=None):
    if disabled_set is None:
        disabled_set = set()
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {})
            }
        }
        for tool in mcp_tools
        if tool["name"] not in disabled_set
    ]

def convert_tools_for_anthropic(mcp_tools, disabled_set=None):
    """Преобразует MCP-инструменты в формат Anthropic Tool."""
    if disabled_set is None:
        disabled_set = set()
    tools = []
    for tool in mcp_tools:
        if tool["name"] in disabled_set:
            continue
        tools.append({
            "name": tool["name"],
            "description": tool.get("description", ""),
            "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}})
        })
    return tools

def load_config():
    default_config = {
        "provider": DEFAULT_PROVIDER,
        "model": DEFAULT_MODEL,
        "api_key": DEFAULT_KEY,
        "base_url": PROVIDER_BASE_URLS[DEFAULT_PROVIDER],
        "input_height": DEFAULT_INPUT_HEIGHT,
        "ssh_host": DEFAULT_SSH_HOST,
        "ssh_user": DEFAULT_SSH_USER,
        "ssh_key_path": DEFAULT_SSH_KEY_PATH,
        "disabled_tools": []
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        except:
            pass
    return default_config

def save_config(**kwargs):
    config = load_config()
    for key, value in kwargs.items():
        if value is not None:
            config[key] = value
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

# ---------- Окно управления инструментами ----------
class ToolsWindow(tk.Toplevel):
    def __init__(self, parent, tools, disabled_set, on_save_callback):
        super().__init__(parent)
        self.title("Tools Manager")
        self.geometry("900x650")
        self.resizable(True, True)
        self.on_save_callback = on_save_callback
        self.disabled_set = set(disabled_set)
        self.tools = tools

        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.search_var.trace_add("write", lambda *args: self._apply_filter())

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))

        style = ttk.Style()
        style.configure("Flat.Treeview", borderwidth=0, relief="flat")
        style.configure("Flat.Treeview.Heading", borderwidth=0, relief="flat", font=("Arial", 10, "bold"))

        columns = ("enabled", "name", "command", "description")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                 style="Flat.Treeview", selectmode="none")
        self.tree.heading("enabled", text="✓")
        self.tree.heading("name", text="Name")
        self.tree.heading("command", text="Command")
        self.tree.heading("description", text="Description")

        self.tree.column("enabled", width=30, anchor=tk.CENTER, stretch=False)
        self.tree.column("name", width=150, stretch=False)
        self.tree.column("command", width=300, stretch=False)
        self.tree.column("description", width=300, stretch=False)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Button-1>", self._on_click)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="Select All", command=self.select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Deselect All", command=self.deselect_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.LEFT, padx=5)

        self._apply_filter()

    def _apply_filter(self):
        query = self.search_var.get().lower()
        filtered = [t for t in self.tools if query in t["name"].lower() or query in t.get("description","").lower()]
        self._refresh_table(filtered)

    def _refresh_table(self, tools):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for tool in tools:
            name = tool["name"]
            cmd = tool.get("command", "")
            desc = tool.get("description", "")
            enabled = name not in self.disabled_set
            symbol = "☑" if enabled else "☐"
            self.tree.insert("", tk.END, values=(symbol, name, cmd, desc))

    def _on_click(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item or column != "#1":
            return
        values = self.tree.item(item, "values")
        if not values:
            return
        name = values[1]
        if name in self.disabled_set:
            self.disabled_set.discard(name)
            self.tree.set(item, column="#1", value="☑")
        else:
            self.disabled_set.add(name)
            self.tree.set(item, column="#1", value="☐")

    def select_all(self):
        self.disabled_set.clear()
        self._apply_filter()

    def deselect_all(self):
        self.disabled_set = {t["name"] for t in self.tools}
        self._apply_filter()

    def save(self):
        self.on_save_callback(list(self.disabled_set))
        self.destroy()

# ---------- Окно настроек (переработанное) ----------
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, config, on_save_callback):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("520x600")
        self.resizable(False, False)
        self.on_save_callback = on_save_callback
        self.config = config

        notebook = ttkb.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Вкладка AI Provider
        provider_frame = ttkb.Frame(notebook)
        notebook.add(provider_frame, text="AI Provider")

        # Выбор провайдера
        ttkb.Label(provider_frame, text="Provider:").pack(pady=5)
        self.provider_var = tk.StringVar(value=config["provider"])
        provider_combo = ttk.Combobox(provider_frame, textvariable=self.provider_var,
                                      values=["deepseek", "openai", "anthropic", "groq", "together", "ollama", "openrouter", "custom"],
                                      state="readonly", width=25)
        provider_combo.pack(pady=5)
        provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        # Base URL
        self.base_url_var = tk.StringVar(value=config.get("base_url", ""))
        self.base_url_frame = ttkb.Frame(provider_frame)
        self.base_url_frame.pack(pady=5)
        ttkb.Label(self.base_url_frame, text="Base URL:").pack(side=tk.LEFT)
        self.base_url_entry = ttkb.Entry(self.base_url_frame, textvariable=self.base_url_var, width=35)
        self.base_url_entry.pack(side=tk.LEFT, padx=5)

        # API Key
        ttkb.Label(provider_frame, text="API Key:").pack(pady=5)
        self.api_key_var = tk.StringVar(value=config["api_key"])
        self.api_key_entry = ttkb.Entry(provider_frame, textvariable=self.api_key_var, width=45, show="*")
        self.api_key_entry.pack(pady=5)

        # Model
        ttkb.Label(provider_frame, text="Model:").pack(pady=5)
        model_frame = ttkb.Frame(provider_frame)
        model_frame.pack(pady=5)
        self.model_var = tk.StringVar(value=config["model"])
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.model_var, state="readonly", width=30)
        self.model_combo.pack(side=tk.LEFT, padx=5)
        refresh_btn = ttkb.Button(model_frame, text="🔄", command=self._refresh_models)
        refresh_btn.pack(side=tk.LEFT)

        # Сообщение о недоступности Anthropic
        self.anthropic_warning = ttkb.Label(provider_frame, text="", bootstyle="warning")
        self.anthropic_warning.pack(pady=5)

        # Вкладка SSH (оставляем как было)
        ssh_frame = ttkb.Frame(notebook)
        notebook.add(ssh_frame, text="SSH Connection")

        ttkb.Label(ssh_frame, text="Host (IP):").pack(pady=5)
        self.ssh_host_var = tk.StringVar(value=config["ssh_host"])
        ttkb.Entry(ssh_frame, textvariable=self.ssh_host_var, width=40).pack(pady=5)

        ttkb.Label(ssh_frame, text="Username:").pack(pady=5)
        self.ssh_user_var = tk.StringVar(value=config["ssh_user"])
        ttkb.Entry(ssh_frame, textvariable=self.ssh_user_var, width=40).pack(pady=5)

        ttkb.Label(ssh_frame, text="Private key path:").pack(pady=5)
        self.ssh_key_var = tk.StringVar(value=config["ssh_key_path"])
        key_frame = ttkb.Frame(ssh_frame)
        key_frame.pack(pady=5)
        ttkb.Entry(key_frame, textvariable=self.ssh_key_var, width=40).pack(side=tk.LEFT)
        ttkb.Button(key_frame, text="Browse", command=self._browse_key).pack(side=tk.LEFT, padx=5)

        self.server_status_var = tk.StringVar(value="Нажмите 'Check' для проверки")
        ttkb.Label(ssh_frame, textvariable=self.server_status_var, bootstyle="info").pack(pady=5)

        btn_frame = ttkb.Frame(ssh_frame)
        btn_frame.pack(pady=10)
        ttkb.Button(btn_frame, text="Check Server", command=self._check_server_status).pack(side=tk.LEFT, padx=5)
        self.install_btn = ttkb.Button(btn_frame, text="Install Server on Debian", command=self._install_server, bootstyle="success")
        self.install_btn.pack(side=tk.LEFT, padx=5)
        ttkb.Button(btn_frame, text="Copy SSH Key", command=self._copy_key, bootstyle="warning").pack(side=tk.LEFT, padx=5)

        # Кнопки Save/Cancel
        bottom_frame = ttkb.Frame(self)
        bottom_frame.pack(pady=15)
        ttkb.Button(bottom_frame, text="Save", command=self._save).pack(side=tk.LEFT, padx=5)
        ttkb.Button(bottom_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

        # Инициализация полей в зависимости от выбранного провайдера
        self._on_provider_change()

    def _on_provider_change(self, event=None):
        provider = self.provider_var.get()
        # Подставляем Base URL, если известен
        if provider in PROVIDER_BASE_URLS:
            self.base_url_var.set(PROVIDER_BASE_URLS[provider])
        else:
            self.base_url_var.set("")
        # Для Anthropic показываем предупреждение, если библиотека не установлена
        if provider == "anthropic" and not ANTHROPIC_AVAILABLE:
            self.anthropic_warning.config(text="⚠️ Установите библиотеку 'anthropic' для поддержки Claude")
        else:
            self.anthropic_warning.config(text="")
        # Очищаем модель и загружаем новый список
        self.model_var.set("")
        self._refresh_models()

    def _refresh_models(self):
        provider = self.provider_var.get()
        api_key = self.api_key_var.get().strip()
        if not api_key:
            return

        if provider == "anthropic":
            # Фиксированный список моделей Anthropic
            models = ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307",
                      "claude-3-5-sonnet-20240620", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]
            self.model_combo['values'] = models
            return

        # Для OpenAI-совместимых провайдеров
        base_url = self.base_url_var.get().strip()
        try:
            client = OpenAI(api_key=api_key, base_url=base_url,
                            http_client=httpx.Client(headers={"Content-Type": "application/json; charset=utf-8"}))
            models = client.models.list()
            model_ids = [m.id for m in models]
            self.model_combo['values'] = model_ids
        except Exception as e:
            # Если не удалось загрузить, оставляем пустой список
            self.model_combo['values'] = []

    def _browse_key(self):
        from tkinter import filedialog
        filename = filedialog.askopenfilename(title="Выберите приватный ключ")
        if filename:
            self.ssh_key_var.set(filename)

    def _check_server_status(self):
        host = self.ssh_host_var.get().strip()
        user = self.ssh_user_var.get().strip()
        if not host or not user:
            self.server_status_var.set("Введите Host и User")
            return
        password = simpledialog.askstring("SSH пароль", f"Введите пароль для {user}@{host}:", show='*')
        if not password:
            return
        def task():
            installed = check_server_installed(host, user, password)
            if installed:
                self.server_status_var.set("✅ Сервер установлен")
                self.install_btn.config(state="disabled")
            else:
                self.server_status_var.set("❌ Сервер не установлен")
                self.install_btn.config(state="normal")
        threading.Thread(target=task, daemon=True).start()

    def _install_server(self):
        host = self.ssh_host_var.get().strip()
        user = self.ssh_user_var.get().strip()
        key_path = self.ssh_key_var.get().strip()
        if not host or not user:
            messagebox.showerror("Ошибка", "Укажите Host и User.")
            return
        if not key_path or not os.path.exists(key_path):
            messagebox.showerror("Ошибка", "Укажите корректный путь к приватному ключу.")
            return
        password = simpledialog.askstring("SSH пароль", f"Введите пароль для {user}@{host}:", show='*')
        if not password:
            return
        self.install_btn.config(state="disabled", text="Установка...")
        def task():
            success, msg = install_server_to_debian(host, user, password, key_path,
                                                    progress_callback=lambda s: self.server_status_var.set(s))
            if success:
                messagebox.showinfo("Успех", msg)
                self.server_status_var.set("✅ Сервер установлен")
            else:
                messagebox.showerror("Ошибка", msg)
                self.server_status_var.set("❌ Ошибка установки")
            self.install_btn.config(state="normal", text="Install Server on Debian")
        threading.Thread(target=task, daemon=True).start()

    def _copy_key(self):
        host = self.ssh_host_var.get().strip()
        user = self.ssh_user_var.get().strip()
        key_path = self.ssh_key_var.get().strip()
        if not host or not user:
            messagebox.showerror("Ошибка", "Укажите Host и Username.")
            return
        password = simpledialog.askstring("SSH пароль", f"Введите пароль для {user}@{host}:", show='*')
        if not password:
            return
        threading.Thread(target=copy_ssh_key_to_server, args=(host, user, key_path, password), daemon=True).start()

    def _save(self):
        provider = self.provider_var.get().strip()
        api_key = self.api_key_var.get().strip()
        model = self.model_var.get().strip()
        base_url = self.base_url_var.get().strip()
        ssh_host = self.ssh_host_var.get().strip()
        ssh_user = self.ssh_user_var.get().strip()
        ssh_key_path = self.ssh_key_var.get().strip()

        if not api_key or not model:
            messagebox.showwarning("Ошибка", "API-ключ и модель обязательны.")
            return
        if not ssh_host or not ssh_user:
            messagebox.showwarning("Ошибка", "SSH Host и Username обязательны.")
            return

        self.on_save_callback(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            ssh_host=ssh_host,
            ssh_user=ssh_user,
            ssh_key_path=ssh_key_path
        )
        self.destroy()

# ---------- Главное окно (адаптировано под разных провайдеров) ----------
class MCPGuiApp:
    def __init__(self, root):
        self.root = root
        root.title("MCP Debian Client")
        root.geometry(DEFAULT_SIZE)

        self.config = load_config()
        self.provider = self.config["provider"]
        self.api_key = self.config["api_key"]
        self.model = self.config["model"]
        self.base_url = self.config["base_url"]
        self.input_height = self.config["input_height"]
        self.ssh_host = self.config["ssh_host"]
        self.ssh_user = self.config["ssh_user"]
        self.ssh_key_path = self.config["ssh_key_path"]
        self.disabled_tools = set(self.config.get("disabled_tools", []))

        menubar = tk.Menu(root)
        root.config(menu=menubar)
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="API & SSH", command=self.open_settings)
        menubar.add_command(label="Tools", command=self.open_tools_window)

        container = ttkb.Frame(root)
        container.pack(fill=tk.BOTH, expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=0)
        container.grid_columnconfigure(0, weight=1)

        self.chat_area = ScrolledText(container, wrap=tk.WORD, autohide=True)
        self.chat_area.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 0))
        self.chat_area.text.config(state='disabled')

        self.input_frame = ttkb.Frame(container, height=self.input_height)
        self.input_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        self.input_frame.pack_propagate(False)
        self.input_frame.grid_propagate(False)
        self.input_frame.config(height=self.input_height)

        self.input_text = tk.Text(self.input_frame, wrap=tk.WORD)
        self.input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        send_btn = ttkb.Button(self.input_frame, text="Send", command=self.send_message)
        send_btn.pack(side=tk.RIGHT, padx=(5, 0), pady=2)

        self._enable_universal_copy_paste(self.chat_area.text)
        self._enable_universal_copy_paste(self.input_text)
        self.input_text.bind("<Return>", self.on_input_return)

        self.status_var = tk.StringVar(value="Disconnected")
        self.status_label = ttkb.Label(root, textvariable=self.status_var, bootstyle="inverse")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.client = None
        self.ai_client = None          # OpenAI или Anthropic
        self.tools_openai = []        # инструменты для OpenAI-совместимых
        self.tools_anthropic = []     # инструменты для Anthropic
        self.messages = []
        self.tools_window = None

        if self.api_key and self.ssh_host and self.ssh_user:
            self.update_status("Connecting...")
            threading.Thread(target=self.init_client, daemon=True).start()
        else:
            self.update_status("Not configured. Open Settings.")
            self.open_settings()

    def update_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    def append_chat(self, sender, text):
        self.chat_area.text.config(state='normal')
        self.chat_area.text.insert(tk.END, f"{sender}: {text}\n\n")
        self.chat_area.text.see(tk.END)
        self.chat_area.text.config(state='disabled')

    def open_settings(self):
        SettingsWindow(self.root, self.config, self.on_settings_save)

    def open_tools_window(self):
        if not self.client:
            messagebox.showwarning("No connection", "Сначала подключитесь к серверу.")
            return
        if self.tools_window is None or not self.tools_window.winfo_exists():
            self.tools_window = ToolsWindow(self.root, self.client.tools, self.disabled_tools, self.on_tools_save)
        else:
            self.tools_window.lift()

    def on_tools_save(self, disabled_list):
        self.disabled_tools = set(disabled_list)
        save_config(disabled_tools=list(self.disabled_tools))
        self._rebuild_tools()

    def _rebuild_tools(self):
        if self.provider == "anthropic":
            self.tools_anthropic = convert_tools_for_anthropic(self.client.tools, self.disabled_tools)
        else:
            self.tools_openai = convert_tools_for_openai(self.client.tools, self.disabled_tools)

    def on_settings_save(self, provider, api_key, model, base_url, ssh_host, ssh_user, ssh_key_path):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path

        save_config(provider=provider, api_key=api_key, model=model, base_url=base_url,
                    ssh_host=ssh_host, ssh_user=ssh_user, ssh_key_path=ssh_key_path,
                    disabled_tools=list(self.disabled_tools))
        if self.client:
            self.client.close()
            self.client = None
        self.ai_client = None
        self.tools_openai = []
        self.tools_anthropic = []
        self.messages = []
        self.update_status("Connecting...")
        self.root.after(500, lambda: threading.Thread(target=self.init_client, daemon=True).start())

    def init_client(self):
        try:
            self.client = MCPClient(self.ssh_user, self.ssh_host, MCP_COMMAND, self.ssh_key_path)
            # Создаём ИИ-клиент в зависимости от провайдера
            if self.provider == "anthropic":
                if not ANTHROPIC_AVAILABLE:
                    raise Exception("Anthropic SDK not installed")
                self.ai_client = Anthropic(api_key=self.api_key)
                self.tools_anthropic = convert_tools_for_anthropic(self.client.tools, self.disabled_tools)
            else:
                # Все остальные используют OpenAI-совместимый API
                self.ai_client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                                        http_client=httpx.Client(headers={"Content-Type": "application/json; charset=utf-8"}))
                self.tools_openai = convert_tools_for_openai(self.client.tools, self.disabled_tools)

            self.update_status(f"Connected ({len(self.client.tools)} tools)")
        except Exception as e:
            self.update_status("Disconnected")
            self.client = None
            messagebox.showerror("Connection Error", str(e))

    def on_input_return(self, event):
        if event.state & 0x1:
            return
        else:
            self.send_message()
            return "break"

    def send_message(self):
        if not self.client or not self.ai_client:
            messagebox.showwarning("Not connected", "Нет подключения.")
            return
        user_text = self.input_text.get("1.0", tk.END).strip()
        if not user_text:
            return
        self.input_text.delete("1.0", tk.END)
        self.append_chat("You", user_text)
        self.messages.append({"role": "user", "content": user_text})
        threading.Thread(target=self.process_response, daemon=True).start()

    def process_response(self):
        try:
            self.update_status("Thinking...")
            while True:
                if self.provider == "anthropic":
                    # Используем Anthropic API
                    response = self.ai_client.messages.create(
                        model=self.model,
                        max_tokens=4096,
                        tools=self.tools_anthropic,
                        messages=self._convert_messages_for_anthropic()
                    )
                    # Обработка ответа Anthropic
                    if response.stop_reason == "tool_use":
                        for block in response.content:
                            if block.type == "tool_use":
                                func_name = block.name
                                func_args = block.input
                                self.append_chat("System", f"Calling {func_name}...")
                                result = self.client.call_tool(func_name, func_args)
                                content_text = ""
                                if result and "content" in result:
                                    for part in result["content"]:
                                        if part.get("type") == "text":
                                            content_text += part["text"]
                                tool_response = content_text or json.dumps(result, ensure_ascii=False)
                                # Добавляем результат в историю
                                self.messages.append({
                                    "role": "assistant",
                                    "content": response.content
                                })
                                self.messages.append({
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "tool_result",
                                            "tool_use_id": block.id,
                                            "content": tool_response
                                        }
                                    ]
                                })
                    else:
                        # Финальный текстовый ответ
                        text = "".join(block.text for block in response.content if block.type == "text")
                        self.append_chat("Claude", text)
                        break
                else:
                    # OpenAI-совместимый вызов
                    response = self.ai_client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        tools=self.tools_openai if self.tools_openai else None
                    )
                    msg = response.choices[0].message
                    self.messages.append(msg)

                    if msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            func_name = tool_call.function.name
                            try:
                                func_args = json.loads(tool_call.function.arguments)
                            except:
                                func_args = {}
                            self.append_chat("System", f"Calling {func_name}...")
                            result = self.client.call_tool(func_name, func_args)
                            content_text = ""
                            if result and "content" in result:
                                for block in result["content"]:
                                    if block.get("type") == "text":
                                        content_text += block.get("text", "")
                            tool_response = content_text or json.dumps(result, ensure_ascii=False)
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": tool_response
                            })
                    else:
                        self.append_chat("AI", msg.content)
                        break
            self.update_status(f"Connected ({len(self.client.tools)} tools)")
        except Exception as e:
            self.append_chat("System", f"Error: {e}")
            self.update_status("Error")

    def _convert_messages_for_anthropic(self):
        """Преобразует историю сообщений в формат Anthropic."""
        anthropic_messages = []
        for msg in self.messages:
            if msg["role"] == "user":
                anthropic_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                # Если это ответ с tool_calls, его нужно преобразовать
                if isinstance(msg.get("content"), list):
                    anthropic_messages.append({"role": "assistant", "content": msg["content"]})
                else:
                    anthropic_messages.append({"role": "assistant", "content": msg["content"]})
            # Пропускаем tool-сообщения, они уже добавлены в user
        return anthropic_messages

    def _enable_universal_copy_paste(self, widget):
        def handle(event):
            if event.state & 4:
                if event.keycode == 54:
                    widget.event_generate("<<Copy>>")
                elif event.keycode == 55:
                    widget.event_generate("<<Paste>>")
                elif event.keycode == 52:
                    widget.event_generate("<<Cut>>")
        widget.bind("<Control-KeyPress>", handle, add="+")

    def on_close(self):
        if self.client:
            self.client.close()
        self.root.destroy()

if __name__ == "__main__":
    root = ttkb.Window(themename="darkly")
    app = MCPGuiApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
