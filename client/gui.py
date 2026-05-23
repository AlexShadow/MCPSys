import subprocess
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import ttkbootstrap as ttkb
from ttkbootstrap.widgets.scrolled import ScrolledText
import httpx
from openai import OpenAI
from datetime import datetime

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
CHATS_DIR = os.path.join(APP_DIR, "chats")
DEFAULT_SIZE = "1280x800"

# ---------- Настройки по умолчанию ----------
DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_KEY = ""
DEFAULT_INPUT_HEIGHT = 80
DEFAULT_SSH_USER = "root"
DEFAULT_SSH_HOST = ""
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_KEY_PATH = os.path.expanduser(r"~/.ssh/id_ed25519")
DEFAULT_SERVER_NAME = "Default"

REMOTE_SERVER_DIR = "/opt/mcp-server"
REMOTE_SERVER_BIN = f"{REMOTE_SERVER_DIR}/mcp-server"
REMOTE_TOOLS_FILE = f"{REMOTE_SERVER_DIR}/tools.toml"
MCP_COMMAND = f"{REMOTE_SERVER_BIN} {REMOTE_TOOLS_FILE}"

PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "ollama": "http://localhost:11434/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}

MAX_TOOL_OUTPUT_CHARS = 2000
MAX_GROUP_PREVIEW_CHARS = 500

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
def copy_ssh_key_to_server(host, port, user, key_path, password=None):
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
        ssh.connect(hostname=host, port=port, username=user, password=password, timeout=15)
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

def check_server_installed(host, port, user, password):
    if not PARAMIKO_AVAILABLE:
        return "unknown"
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, port=port, username=user, password=password, timeout=10)
        stdin, stdout, stderr = ssh.exec_command(f"test -f {REMOTE_SERVER_BIN} && echo 'yes' || echo 'no'")
        result = stdout.read().decode().strip()
        ssh.close()
        return result == "yes"
    except:
        return False

def install_server_to_debian(host, port, user, password, key_path, progress_callback=None):
    if not PARAMIKO_AVAILABLE:
        raise RuntimeError("paramiko не установлен")

    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    local_bin = os.path.join(base_path, "mcp-server")
    local_tools = os.path.join(base_path, "tools.toml")

    if not os.path.exists(local_bin):
        local_bin = os.path.join(os.getcwd(), "mcp-server")
    if not os.path.exists(local_tools):
        local_tools = os.path.join(os.getcwd(), "tools.toml")

    if not os.path.exists(local_bin):
        raise FileNotFoundError(f"mcp-server not found in {base_path} or {os.getcwd()}")
    if not os.path.exists(local_tools):
        raise FileNotFoundError(f"tools.toml not found in {base_path} or {os.getcwd()}")

    pub_key_path = key_path + ".pub"
    if not os.path.exists(pub_key_path):
        raise FileNotFoundError(f"Public key not found: {pub_key_path}")
    with open(pub_key_path, 'r', encoding='utf-8') as f:
        pub_key = f.read().strip()

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, port=port, username=user, password=password, timeout=15)
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
    def __init__(self, ssh_user, ssh_host, ssh_port, command, key_path=None):
        if not ssh_host:
            raise ValueError("SSH host не задан")
        ssh_target = f"{ssh_user}@{ssh_host}"
        ssh_args = [
            "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
            "-p", str(ssh_port)
        ]
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

def convert_tools_for_openai(mcp_tools, server_name, disabled_set=None):
    if disabled_set is None:
        disabled_set = set()
    result = []
    for tool in mcp_tools:
        if tool["name"] in disabled_set:
            continue
        result.append({
            "type": "function",
            "function": {
                "name": f"{server_name}__{tool['name']}",
                "description": f"[{server_name}] {tool.get('description', '')}",
                "parameters": tool.get("inputSchema", {})
            }
        })
    return result

def convert_tools_for_anthropic(mcp_tools, server_name, disabled_set=None):
    if disabled_set is None:
        disabled_set = set()
    tools = []
    for tool in mcp_tools:
        if tool["name"] in disabled_set:
            continue
        tools.append({
            "name": f"{server_name}__{tool['name']}",
            "description": f"[{server_name}] {tool.get('description', '')}",
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
        "servers": {
            DEFAULT_SERVER_NAME: {
                "ssh_host": DEFAULT_SSH_HOST,
                "ssh_port": DEFAULT_SSH_PORT,
                "ssh_user": DEFAULT_SSH_USER,
                "ssh_key_path": DEFAULT_SSH_KEY_PATH
            }
        },
        "active_server": DEFAULT_SERVER_NAME,
        "disabled_tools": [],
        "active_chat": None
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                servers = config.get("servers", None)
                if isinstance(servers, list):
                    new_servers = {}
                    for i, srv in enumerate(servers):
                        name = srv.get("name", f"Server_{i+1}")
                        new_servers[name] = {
                            "ssh_host": srv.get("ssh_host", ""),
                            "ssh_port": srv.get("ssh_port", 22),
                            "ssh_user": srv.get("ssh_user", "root"),
                            "ssh_key_path": srv.get("ssh_key_path", "")
                        }
                    config["servers"] = new_servers
                    old_active = config.get("active_server", "")
                    if old_active not in new_servers:
                        config["active_server"] = list(new_servers.keys())[0] if new_servers else DEFAULT_SERVER_NAME
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

# ---------- Управление чатами ----------
def get_chat_list():
    if not os.path.exists(CHATS_DIR):
        os.makedirs(CHATS_DIR)
    files = [f for f in os.listdir(CHATS_DIR) if f.endswith('.json')]
    files.sort(reverse=True)
    return files

def get_chat_path(chat_id):
    return os.path.join(CHATS_DIR, chat_id)

def load_chat_messages(chat_id):
    path = get_chat_path(chat_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_chat_messages(chat_id, messages):
    path = get_chat_path(chat_id)
    try:
        serializable = []
        for msg in messages:
            if isinstance(msg, dict):
                serializable.append(msg)
            else:
                serializable.append(msg.model_dump() if hasattr(msg, 'model_dump') else msg.to_dict())
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save chat {chat_id}: {e}")

def create_new_chat_file():
    chat_id = f"chat_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
    save_chat_messages(chat_id, [])
    return chat_id

# ---------- Универсальное копирование/вставка ----------
def bind_universal_copy_paste(widget):
    def handle(event):
        if event.state & 4:
            if event.char == '\x03':
                widget.event_generate("<<Copy>>")
            elif event.char == '\x16':
                widget.event_generate("<<Paste>>")
            elif event.char == '\x18':
                widget.event_generate("<<Cut>>")
            elif event.char == '\x01':
                widget.event_generate("<<SelectAll>>")
    widget.bind("<Control-KeyPress>", handle, add="+")

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
        bind_universal_copy_paste(self.search_entry)
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

# ---------- Окно настроек ----------
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, config, on_save_callback):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("550x700")
        self.resizable(False, False)
        self.on_save_callback = on_save_callback
        self.config = config

        notebook = ttkb.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Вкладка AI Provider
        provider_frame = ttkb.Frame(notebook)
        notebook.add(provider_frame, text="AI Provider")

        ttkb.Label(provider_frame, text="Provider:").pack(pady=5)
        self.provider_var = tk.StringVar(value=config["provider"])
        provider_combo = ttk.Combobox(provider_frame, textvariable=self.provider_var,
                                      values=["deepseek", "openai", "anthropic", "groq", "together", "ollama", "openrouter", "custom"],
                                      state="readonly", width=25)
        provider_combo.pack(pady=5)
        provider_combo.bind("<<ComboboxSelected>>", self._on_provider_change)

        self.base_url_var = tk.StringVar(value=config.get("base_url", ""))
        self.base_url_frame = ttkb.Frame(provider_frame)
        self.base_url_frame.pack(pady=5)
        ttkb.Label(self.base_url_frame, text="Base URL:").pack(side=tk.LEFT)
        self.base_url_entry = ttkb.Entry(self.base_url_frame, textvariable=self.base_url_var, width=35)
        self.base_url_entry.pack(side=tk.LEFT, padx=5)
        bind_universal_copy_paste(self.base_url_entry)

        ttkb.Label(provider_frame, text="API Key:").pack(pady=5)
        self.api_key_var = tk.StringVar(value=config["api_key"])
        self.api_key_entry = ttkb.Entry(provider_frame, textvariable=self.api_key_var, width=45, show="*")
        self.api_key_entry.pack(pady=5)
        bind_universal_copy_paste(self.api_key_entry)

        ttkb.Label(provider_frame, text="Model:").pack(pady=5)
        model_frame = ttkb.Frame(provider_frame)
        model_frame.pack(pady=5)
        self.model_var = tk.StringVar(value=config["model"])
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.model_var, state="readonly", width=30)
        self.model_combo.pack(side=tk.LEFT, padx=5)
        refresh_btn = ttkb.Button(model_frame, text="🔄", command=self._refresh_models)
        refresh_btn.pack(side=tk.LEFT)

        self.anthropic_warning = ttkb.Label(provider_frame, text="", bootstyle="warning")
        self.anthropic_warning.pack(pady=5)

        # Вкладка SSH / Servers
        ssh_frame = ttkb.Frame(notebook)
        notebook.add(ssh_frame, text="Servers")

        list_frame = ttkb.Frame(ssh_frame)
        list_frame.pack(fill=tk.X, padx=5, pady=5)
        ttkb.Label(list_frame, text="Saved Servers:").pack(side=tk.LEFT)
        self.server_listbox = tk.Listbox(list_frame, height=4, exportselection=False)
        self.server_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.server_listbox.bind('<<ListboxSelect>>', self._on_server_select)
        btn_list_frame = ttkb.Frame(list_frame)
        btn_list_frame.pack(side=tk.LEFT)
        ttkb.Button(btn_list_frame, text="+", width=3, command=self._add_server).pack(pady=2)
        ttkb.Button(btn_list_frame, text="−", width=3, command=self._remove_server).pack(pady=2)

        ttkb.Label(ssh_frame, text="Server Name:").pack(pady=5)
        self.server_name_var = tk.StringVar()
        name_frame = ttkb.Frame(ssh_frame)
        name_frame.pack(pady=5)
        self.server_name_entry = ttkb.Entry(name_frame, textvariable=self.server_name_var, width=30)
        self.server_name_entry.pack(side=tk.LEFT, padx=5)
        bind_universal_copy_paste(self.server_name_entry)

        ttkb.Label(ssh_frame, text="Host (IP):").pack(pady=5)
        self.ssh_host_var = tk.StringVar()
        self.ssh_host_entry = ttkb.Entry(ssh_frame, textvariable=self.ssh_host_var, width=40)
        self.ssh_host_entry.pack(pady=5)
        bind_universal_copy_paste(self.ssh_host_entry)

        port_user_frame = ttkb.Frame(ssh_frame)
        port_user_frame.pack(pady=5, fill=tk.X)
        ttkb.Label(port_user_frame, text="Port:").pack(side=tk.LEFT)
        self.ssh_port_var = tk.IntVar(value=22)
        self.port_entry = ttkb.Entry(port_user_frame, textvariable=self.ssh_port_var, width=8)
        self.port_entry.pack(side=tk.LEFT, padx=5)
        bind_universal_copy_paste(self.port_entry)
        ttkb.Label(port_user_frame, text="Username:").pack(side=tk.LEFT, padx=(15, 0))
        self.ssh_user_var = tk.StringVar()
        self.user_entry = ttkb.Entry(port_user_frame, textvariable=self.ssh_user_var, width=20)
        self.user_entry.pack(side=tk.LEFT, padx=5)
        bind_universal_copy_paste(self.user_entry)

        ttkb.Label(ssh_frame, text="Private key path:").pack(pady=5)
        key_frame = ttkb.Frame(ssh_frame)
        key_frame.pack(pady=5)
        self.ssh_key_var = tk.StringVar()
        self.key_entry = ttkb.Entry(key_frame, textvariable=self.ssh_key_var, width=40)
        self.key_entry.pack(side=tk.LEFT)
        bind_universal_copy_paste(self.key_entry)
        ttkb.Button(key_frame, text="Browse", command=self._browse_key).pack(side=tk.LEFT, padx=5)
        ttkb.Button(key_frame, text="Generate Key", command=self._generate_ssh_key).pack(side=tk.LEFT, padx=5)

        self.server_status_var = tk.StringVar(value="Нажмите 'Check' для проверки")
        ttkb.Label(ssh_frame, textvariable=self.server_status_var, bootstyle="info").pack(pady=5)

        btn_frame = ttkb.Frame(ssh_frame)
        btn_frame.pack(pady=10)
        ttkb.Button(btn_frame, text="Check Server", command=self._check_server_status).pack(side=tk.LEFT, padx=5)
        self.install_btn = ttkb.Button(btn_frame, text="Install Server on Debian", command=self._install_server, bootstyle="success")
        self.install_btn.pack(side=tk.LEFT, padx=5)
        ttkb.Button(btn_frame, text="Copy SSH Key", command=self._copy_key, bootstyle="warning").pack(side=tk.LEFT, padx=5)

        bottom_frame = ttkb.Frame(self)
        bottom_frame.pack(pady=15)
        ttkb.Button(bottom_frame, text="Save", command=self._save).pack(side=tk.LEFT, padx=5)
        ttkb.Button(bottom_frame, text="Close", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.servers = config.get("servers", {})
        self._refresh_server_list()
        self._on_provider_change()

    def _on_provider_change(self, event=None):
        provider = self.provider_var.get()
        if provider in PROVIDER_BASE_URLS:
            self.base_url_var.set(PROVIDER_BASE_URLS[provider])
        else:
            self.base_url_var.set("")
        if provider == "anthropic" and not ANTHROPIC_AVAILABLE:
            self.anthropic_warning.config(text="⚠️ Установите библиотеку 'anthropic' для поддержки Claude")
        else:
            self.anthropic_warning.config(text="")
        self.model_var.set("")
        self._refresh_models()

    def _refresh_models(self):
        provider = self.provider_var.get()
        api_key = self.api_key_var.get().strip()
        if not api_key:
            return
        if provider == "anthropic":
            models = ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307",
                      "claude-3-5-sonnet-20240620", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]
            self.model_combo['values'] = models
            return
        base_url = self.base_url_var.get().strip()
        try:
            client = OpenAI(api_key=api_key, base_url=base_url,
                            http_client=httpx.Client(headers={"Content-Type": "application/json; charset=utf-8"}))
            models = client.models.list()
            model_ids = [m.id for m in models]
            self.model_combo['values'] = model_ids
        except Exception as e:
            self.model_combo['values'] = []

    def _refresh_server_list(self):
        self.server_listbox.delete(0, tk.END)
        for name in self.servers:
            self.server_listbox.insert(tk.END, name)

    def _on_server_select(self, event):
        selection = self.server_listbox.curselection()
        if not selection:
            return
        name = self.server_listbox.get(selection[0])
        server = self.servers.get(name, {})
        self.server_name_var.set(name)
        self.ssh_host_var.set(server.get("ssh_host", ""))
        self.ssh_port_var.set(server.get("ssh_port", 22))
        self.ssh_user_var.set(server.get("ssh_user", "root"))
        self.ssh_key_var.set(server.get("ssh_key_path", ""))

    def _add_server(self):
        name = self.server_name_var.get().strip()
        if not name:
            name = simpledialog.askstring("New Server", "Enter server name:")
        if not name or name in self.servers:
            return
        self.servers[name] = {
            "ssh_host": self.ssh_host_var.get().strip(),
            "ssh_port": self.ssh_port_var.get(),
            "ssh_user": self.ssh_user_var.get().strip(),
            "ssh_key_path": self.ssh_key_var.get().strip()
        }
        self._refresh_server_list()
        self.server_name_var.set(name)

    def _remove_server(self):
        selection = self.server_listbox.curselection()
        if not selection:
            return
        name = self.server_listbox.get(selection[0])
        if messagebox.askyesno("Delete Server", f"Delete server '{name}'?"):
            del self.servers[name]
            self._refresh_server_list()
            if self.server_name_var.get() == name:
                self.server_name_var.set("")

    def _browse_key(self):
        filename = filedialog.askopenfilename(
            parent=self,
            title="Выберите приватный ключ",
            filetypes=[("Private keys", "*.pem *.key *.ppk"), ("All files", "*.*")]
        )
        if filename:
            self.ssh_key_var.set(filename)

    def _generate_ssh_key(self):
        key_dir = os.path.expanduser("~/.ssh")
        os.makedirs(key_dir, exist_ok=True)
        key_path = os.path.join(key_dir, "id_ed25519")
        def task():
            try:
                subprocess.run(
                    ["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-q"],
                    check=True, capture_output=True, text=True
                )
                self.ssh_key_var.set(key_path)
                messagebox.showinfo("Успех", f"Ключ сгенерирован:\n{key_path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сгенерировать ключ:\n{e}")
        threading.Thread(target=task, daemon=True).start()

    def _check_server_status(self):
        host = self.ssh_host_var.get().strip()
        port = self.ssh_port_var.get()
        user = self.ssh_user_var.get().strip()
        if not host or not user:
            self.server_status_var.set("Введите Host и User")
            return
        password = simpledialog.askstring("SSH пароль", f"Введите пароль для {user}@{host}:", show='*')
        if not password:
            return
        def task():
            installed = check_server_installed(host, port, user, password)
            if installed:
                self.server_status_var.set("✅ Сервер установлен")
                self.install_btn.config(state="disabled")
            else:
                self.server_status_var.set("❌ Сервер не установлен")
                self.install_btn.config(state="normal")
        threading.Thread(target=task, daemon=True).start()

    def _install_server(self):
        host = self.ssh_host_var.get().strip()
        port = self.ssh_port_var.get()
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
            success, msg = install_server_to_debian(host, port, user, password, key_path,
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
        port = self.ssh_port_var.get()
        user = self.ssh_user_var.get().strip()
        key_path = self.ssh_key_var.get().strip()
        if not host or not user:
            messagebox.showerror("Ошибка", "Укажите Host и Username.")
            return
        password = simpledialog.askstring("SSH пароль", f"Введите пароль для {user}@{host}:", show='*')
        if not password:
            return
        threading.Thread(target=copy_ssh_key_to_server, args=(host, port, user, key_path, password), daemon=True).start()

    def _save(self):
        provider = self.provider_var.get().strip()
        api_key = self.api_key_var.get().strip()
        model = self.model_var.get().strip()
        base_url = self.base_url_var.get().strip()
        server_name = self.server_name_var.get().strip()
        if server_name:
            self.servers[server_name] = {
                "ssh_host": self.ssh_host_var.get().strip(),
                "ssh_port": self.ssh_port_var.get(),
                "ssh_user": self.ssh_user_var.get().strip(),
                "ssh_key_path": self.ssh_key_var.get().strip()
            }

        if not api_key or not model:
            messagebox.showwarning("Ошибка", "API-ключ и модель обязательны.")
            return

        self.on_save_callback(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            servers=self.servers,
            active_server=self.server_name_var.get().strip()
        )

# ---------- Виджет для группировки команд ----------
class ToolGroupWidget(tk.Frame):
    def __init__(self, parent, expanded=False):
        super().__init__(parent, bd=0, highlightthickness=0)
        self.expanded = expanded
        self.count = 0
        self.results = []

        self.header_var = tk.StringVar(value=f"⚙️ System: 0 commands [▶]")
        self.header_btn = ttk.Label(self, textvariable=self.header_var, foreground="#4FC3F7", cursor="hand2")
        self.header_btn.pack(anchor="w")
        self.header_btn.bind("<Button-1>", self.toggle)

        self.text = tk.Text(self, wrap=tk.WORD, state="disabled", height=8, bg="#2b2b2b", fg="white")
        self.text.pack(fill=tk.BOTH, expand=True)
        self._initially_collapsed = not expanded

    def toggle(self, event=None):
        self.expanded = not self.expanded
        if self.expanded:
            self.text.pack(fill=tk.BOTH, expand=True)
        else:
            self.text.pack_forget()
        self._update_header()

    def add_result(self, name, args, full_text):
        self.count += 1
        self.results.append((name, args, full_text))
        self.text.config(state="normal")
        args_str = json.dumps(args) if args else ""
        preview = full_text[:MAX_GROUP_PREVIEW_CHARS]
        if len(full_text) > MAX_GROUP_PREVIEW_CHARS:
            preview += "\n... [truncated]"
        self.text.insert(tk.END, f"🔧 {name}({args_str})\n{preview}\n\n")
        self.text.see(tk.END)
        self.text.config(state="disabled")
        if self._initially_collapsed:
            self.text.pack_forget()
            self._initially_collapsed = False
        self._update_header()

    def _update_header(self):
        marker = "▼" if self.expanded else "▶"
        self.header_var.set(f"⚙️ System: {self.count} command{'s' if self.count>1 else ''} [{marker}]")

# ---------- Главное окно ----------
class MCPGuiApp:
    def __init__(self, root):
        self.root = root
        root.title("MCPSys")
        root.geometry(DEFAULT_SIZE)

        self.config = load_config()
        self.provider = self.config["provider"]
        self.api_key = self.config["api_key"]
        self.model = self.config["model"]
        self.base_url = self.config["base_url"]
        self.input_height = self.config["input_height"]
        self.servers = self.config.get("servers", {})
        if isinstance(self.servers, list):
            new_servers = {}
            for i, srv in enumerate(self.servers):
                name = srv.get("name", f"Server_{i+1}")
                new_servers[name] = {
                    "ssh_host": srv.get("ssh_host", ""),
                    "ssh_port": srv.get("ssh_port", 22),
                    "ssh_user": srv.get("ssh_user", "root"),
                    "ssh_key_path": srv.get("ssh_key_path", "")
                }
            self.servers = new_servers
            self.config["servers"] = new_servers
        self.active_server = self.config.get("active_server", "")
        if self.active_server not in self.servers:
            self.active_server = list(self.servers.keys())[0] if self.servers else ""
        self.disabled_tools = set(self.config.get("disabled_tools", []))

        self.stop_event = threading.Event()
        self.processing = False
        self.current_chat_id = None
        self.tool_expanded = False
        self.current_tool_group = None
        self.settings_window = None

        # Множественные клиенты
        self.clients = {}  # server_name -> MCPClient
        self.tools_openai = []
        self.tools_anthropic = []
        self.ai_client = None

        # Меню
        menubar = tk.Menu(root)
        root.config(menu=menubar)
        chat_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Chat", menu=chat_menu)
        chat_menu.add_command(label="Save Chat As...", command=self.save_chat_as)
        chat_menu.add_command(label="Load Chat...", command=self.load_chat_from_file)
        chat_menu.add_separator()
        chat_menu.add_command(label="Expand All Tools", command=self.expand_all_tools)
        chat_menu.add_command(label="Collapse All Tools", command=self.collapse_all_tools)
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="API & Servers", command=self.open_settings)
        menubar.add_command(label="Tools", command=self.open_tools_window)

        # Основной контейнер
        main_container = ttkb.Frame(root)
        main_container.pack(fill=tk.BOTH, expand=True)

        # Левая панель
        self.left_frame = ttkb.Frame(main_container, width=220)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.left_frame.pack_propagate(False)

        ttkb.Label(self.left_frame, text="Servers", font=("Arial", 12, "bold")).pack(pady=5)
        self.server_listbox = tk.Listbox(self.left_frame, height=4, exportselection=False, selectmode=tk.MULTIPLE)
        self.server_listbox.pack(fill=tk.X, padx=5, pady=(0,5))
        self.server_listbox.bind('<<ListboxSelect>>', self.on_server_selected)

        ttkb.Label(self.left_frame, text="Chats", font=("Arial", 12, "bold")).pack(pady=5)
        self.new_chat_btn = ttkb.Button(self.left_frame, text="+ New Chat", command=self.create_new_chat, bootstyle="success")
        self.new_chat_btn.pack(pady=5, padx=5, fill=tk.X)

        self.chat_listbox = tk.Listbox(self.left_frame, selectmode=tk.SINGLE, exportselection=False)
        self.chat_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.chat_listbox.bind('<<ListboxSelect>>', self.on_chat_selected)

        # Правая часть (чат)
        right_frame = ttkb.Frame(main_container)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        container = ttkb.Frame(right_frame)
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

        self.stop_btn = ttkb.Button(self.input_frame, text="Stop", command=self.stop_generation, bootstyle="danger")
        self.stop_btn.pack(side=tk.RIGHT, padx=(5, 0), pady=2)
        self.stop_btn.config(state="disabled")

        send_btn = ttkb.Button(self.input_frame, text="Send", command=self.send_message)
        send_btn.pack(side=tk.RIGHT, padx=(5, 0), pady=2)

        bind_universal_copy_paste(self.chat_area.text)
        bind_universal_copy_paste(self.input_text)
        self.input_text.bind("<Return>", self.on_input_return)

        self.status_var = tk.StringVar(value="Disconnected")
        self.status_label = ttkb.Label(root, textvariable=self.status_var, bootstyle="inverse")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.messages = []
        self.tools_window = None
        self.processing_thread = None

        self._refresh_server_list()
        self.refresh_chat_list()

        active_chat = self.config.get("active_chat")
        if active_chat and os.path.exists(get_chat_path(active_chat)):
            self.load_chat_by_id(active_chat)
        else:
            self.create_new_chat()

        if self.api_key:
            self.update_status("Connecting...")
            threading.Thread(target=self.connect_all_servers, daemon=True).start()
        else:
            self.update_status("Not configured. Open Settings.")

    def _refresh_server_list(self):
        self.server_listbox.delete(0, tk.END)
        for name in self.servers:
            self.server_listbox.insert(tk.END, name)
        # Выделяем все серверы, у которых есть host
        for i, name in enumerate(self.servers):
            if self.servers[name].get("ssh_host", ""):
                self.server_listbox.selection_set(i)

    def connect_all_servers(self):
        # Закрываем старые соединения
        for client in self.clients.values():
            try:
                client.close()
            except:
                pass
        self.clients.clear()
        self.tools_openai = []
        self.tools_anthropic = []

        # Создаём AI-клиент
        if self.provider == "anthropic":
            if not ANTHROPIC_AVAILABLE:
                self.update_status("Anthropic SDK not installed")
                return
            self.ai_client = Anthropic(api_key=self.api_key)
        else:
            self.ai_client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                                    http_client=httpx.Client(
                                        headers={"Content-Type": "application/json; charset=utf-8"}))

        # Подключаемся ко всем серверам, у которых заполнен host
        connected = 0
        for name, server in self.servers.items():
            host = server.get("ssh_host", "")
            if not host:
                continue
            try:
                client = MCPClient(
                    server.get("ssh_user", "root"),
                    host,
                    server.get("ssh_port", 22),
                    MCP_COMMAND,
                    server.get("ssh_key_path", "")
                )
                self.clients[name] = client
                # Добавляем инструменты
                if self.provider == "anthropic":
                    self.tools_anthropic.extend(
                        convert_tools_for_anthropic(client.tools, name, self.disabled_tools)
                    )
                else:
                    self.tools_openai.extend(
                        convert_tools_for_openai(client.tools, name, self.disabled_tools)
                    )
                connected += 1
            except Exception as e:
                print(f"Failed to connect to {name}: {e}")

        if connected > 0:
            self.update_status(
                f"Connected ({connected} servers, {len(self.tools_openai) + len(self.tools_anthropic)} tools)")
        else:
            self.update_status("No servers connected")

    def on_server_selected(self, event):
        # Множественный выбор — пока ничего не делаем, все серверы уже подключены
        pass

    def refresh_chat_list(self):
        self.chat_listbox.delete(0, tk.END)
        for chat_file in get_chat_list():
            name = chat_file.replace('.json', '')
            self.chat_listbox.insert(tk.END, name)
        if self.current_chat_id:
            current_name = self.current_chat_id.replace('.json', '')
            for i in range(self.chat_listbox.size()):
                if self.chat_listbox.get(i) == current_name:
                    self.chat_listbox.selection_set(i)
                    self.chat_listbox.see(i)
                    break

    def create_new_chat(self):
        if self.current_chat_id and self.messages:
            save_chat_messages(self.current_chat_id, self.messages)
        new_id = create_new_chat_file()
        self.load_chat_by_id(new_id)

    def load_chat_by_id(self, chat_id):
        if self.current_chat_id and self.messages:
            save_chat_messages(self.current_chat_id, self.messages)
        self.current_chat_id = chat_id
        self.messages = load_chat_messages(chat_id)
        self.display_messages()
        self.update_status(f"Chat: {chat_id.replace('.json','')}")
        save_config(active_chat=chat_id)
        self.refresh_chat_list()

    def display_messages(self):
        self.chat_area.text.config(state='normal')
        self.chat_area.text.delete('1.0', tk.END)
        for msg in self.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                self.chat_area.text.insert(tk.END, f"You: {content}\n\n")
            elif role == "assistant":
                self.chat_area.text.insert(tk.END, f"AI: {content}\n\n")
            elif role == "tool":
                self.chat_area.text.insert(tk.END, f"Tool: {content}\n\n")
        self.chat_area.text.see(tk.END)
        self.chat_area.text.config(state='disabled')

    def on_chat_selected(self, event):
        selection = self.chat_listbox.curselection()
        if not selection:
            return
        chat_name = self.chat_listbox.get(selection[0])
        chat_id = chat_name + ".json"
        if chat_id != self.current_chat_id:
            self.load_chat_by_id(chat_id)

    def update_status(self, text):
        self.status_var.set(text)
        self.root.update_idletasks()

    def append_chat(self, sender, text):
        self.chat_area.text.config(state='normal')
        self.chat_area.text.insert(tk.END, f"{sender}: {text}\n\n")
        self.chat_area.text.see(tk.END)
        self.chat_area.text.config(state='disabled')

    def start_or_update_tool_group(self, func_name, func_args, full_text):
        self.chat_area.text.config(state='normal')
        if self.current_tool_group is None:
            self.current_tool_group = ToolGroupWidget(self.chat_area.text, expanded=self.tool_expanded)
            self.chat_area.text.window_create(tk.END, window=self.current_tool_group, stretch=True)
            self.chat_area.text.insert(tk.END, "\n")
        self.current_tool_group.add_result(func_name, func_args, full_text)
        self.chat_area.text.see(tk.END)
        self.chat_area.text.config(state='disabled')

    def finalize_tool_group(self):
        self.current_tool_group = None

    def expand_all_tools(self):
        self._set_all_tools_expanded(True)

    def collapse_all_tools(self):
        self._set_all_tools_expanded(False)

    def _set_all_tools_expanded(self, expand):
        for widget in self.chat_area.text.winfo_children():
            if isinstance(widget, ToolGroupWidget):
                if widget.expanded != expand:
                    widget.toggle()

    def new_chat(self):
        self.create_new_chat()

    def save_chat_as(self):
        file_path = filedialog.asksaveasfilename(
            title="Сохранить текущий чат как",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.messages, f, ensure_ascii=False, indent=2)
                messagebox.showinfo("Успех", f"Чат сохранён в {file_path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")

    def load_chat_from_file(self):
        file_path = filedialog.askopenfilename(
            title="Загрузить чат из файла",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if not isinstance(loaded, list):
                raise ValueError("Неверный формат")
            if self.current_chat_id and self.messages:
                save_chat_messages(self.current_chat_id, self.messages)
            new_id = create_new_chat_file()
            self.current_chat_id = new_id
            self.messages = loaded
            save_chat_messages(new_id, loaded)
            self.display_messages()
            self.update_status(f"Chat: {new_id.replace('.json','')}")
            save_config(active_chat=new_id)
            self.refresh_chat_list()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить: {e}")

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        self.settings_window = SettingsWindow(self.root, self.config, self.on_settings_save)
        self.settings_window.protocol("WM_DELETE_WINDOW", self._on_settings_close)

    def _on_settings_close(self):
        self.settings_window = None

    def open_tools_window(self):
        if not self.clients:
            messagebox.showwarning("No connection", "Сначала подключитесь к серверу.")
            return
        # Собираем все инструменты со всех серверов
        all_tools = []
        for name, client in self.clients.items():
            for tool in client.tools:
                all_tools.append(tool)
        if self.tools_window is None or not self.tools_window.winfo_exists():
            self.tools_window = ToolsWindow(self.root, all_tools, self.disabled_tools, self.on_tools_save)
        else:
            self.tools_window.lift()

    def on_tools_save(self, disabled_list):
        self.disabled_tools = set(disabled_list)
        save_config(disabled_tools=list(self.disabled_tools))
        # Перестраиваем инструменты
        self.tools_openai = []
        self.tools_anthropic = []
        for name, client in self.clients.items():
            if self.provider == "anthropic":
                self.tools_anthropic.extend(
                    convert_tools_for_anthropic(client.tools, name, self.disabled_tools)
                )
            else:
                self.tools_openai.extend(
                    convert_tools_for_openai(client.tools, name, self.disabled_tools)
                )
        self.update_status(
            f"Connected ({len(self.clients)} servers, {len(self.tools_openai) + len(self.tools_anthropic)} tools)")

    def on_settings_save(self, provider, api_key, model, base_url, servers, active_server):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.servers = servers
        self.active_server = active_server

        save_config(provider=provider, api_key=api_key, model=model, base_url=base_url,
                    servers=servers, active_server=active_server,
                    disabled_tools=list(self.disabled_tools))

        self.messages = []
        self._refresh_server_list()
        self.update_status("Connecting...")
        self.root.after(500, lambda: threading.Thread(target=self.connect_all_servers, daemon=True).start())

    def on_input_return(self, event):
        if event.state & 0x1:
            return
        else:
            self.send_message()
            return "break"

    def stop_generation(self):
        self.stop_event.set()
        self.stop_btn.config(state="disabled")

    def send_message(self):
        if self.processing:
            messagebox.showwarning("Подождите", "Идёт обработка предыдущего запроса.")
            return
        if not self.clients or not self.ai_client:
            messagebox.showwarning("Not connected", "Нет подключения.")
            return
        user_text = self.input_text.get("1.0", tk.END).strip()
        if not user_text:
            return
        self.input_text.delete("1.0", tk.END)
        self.append_chat("You", user_text)
        self.messages.append({"role": "user", "content": user_text})
        if self.current_chat_id:
            save_chat_messages(self.current_chat_id, self.messages)

        self.stop_event.clear()
        self.stop_btn.config(state="normal")
        self.processing = True
        self.finalize_tool_group()

        self.processing_thread = threading.Thread(target=self.process_response, daemon=True)
        self.processing_thread.start()

    def process_response(self):
        try:
            self.update_status("Thinking...")
            while not self.stop_event.is_set():
                if self.provider == "anthropic":
                    response = self.ai_client.messages.create(
                        model=self.model,
                        max_tokens=4096,
                        tools=self.tools_anthropic,
                        messages=self._convert_messages_for_anthropic()
                    )
                    if self.stop_event.is_set():
                        break
                    if response.stop_reason == "tool_use":
                        for block in response.content:
                            if block.type == "tool_use":
                                full_name = block.name  # server__tool
                                parts = full_name.split("__", 1)
                                server_name = parts[0]
                                tool_name = parts[1] if len(parts) > 1 else full_name
                                func_args = block.input
                                result = None
                                if server_name in self.clients:
                                    result = self.clients[server_name].call_tool(tool_name, func_args)
                                full_text = ""
                                if result and "content" in result:
                                    for part in result["content"]:
                                        if part.get("type") == "text":
                                            full_text += part["text"]
                                short_text = full_text[:MAX_TOOL_OUTPUT_CHARS]
                                if len(full_text) > MAX_TOOL_OUTPUT_CHARS:
                                    short_text += "\n... [truncated]"
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
                                            "content": short_text
                                        }
                                    ]
                                })
                                self.start_or_update_tool_group(f"{server_name}:{tool_name}", func_args, full_text)
                    else:
                        text = "".join(block.text for block in response.content if block.type == "text")
                        self.append_chat("Claude", text)
                        break
                else:
                    response = self.ai_client.chat.completions.create(
                        model=self.model,
                        messages=self.messages,
                        tools=self.tools_openai if self.tools_openai else None
                    )
                    if self.stop_event.is_set():
                        break
                    msg = response.choices[0].message
                    self.messages.append(msg)

                    if msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            if self.stop_event.is_set():
                                break
                            full_name = tool_call.function.name
                            parts = full_name.split("__", 1)
                            server_name = parts[0]
                            tool_name = parts[1] if len(parts) > 1 else full_name
                            try:
                                func_args = json.loads(tool_call.function.arguments)
                            except:
                                func_args = {}
                            result = None
                            if server_name in self.clients:
                                try:
                                    result = self.clients[server_name].call_tool(tool_name, func_args)
                                except Exception as e:
                                    result = {"content": [{"type": "text", "text": str(e)}]}
                            full_text = ""
                            if result and "content" in result:
                                for block in result["content"]:
                                    if block.get("type") == "text":
                                        full_text += block["text"]

                            short_text = full_text[:MAX_TOOL_OUTPUT_CHARS]
                            if len(full_text) > MAX_TOOL_OUTPUT_CHARS:
                                short_text += "\n... [truncated]"
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": short_text
                            })
                            self.start_or_update_tool_group(f"{server_name}:{tool_name}", func_args, full_text)
                    else:
                        self.append_chat("AI", msg.content)
                        break
            if self.current_chat_id:
                save_chat_messages(self.current_chat_id, self.messages)
            if self.stop_event.is_set():
                self.append_chat("System", "Stopped")
            self.update_status(f"Connected ({len(self.clients)} servers)")
        except Exception as e:
            self.append_chat("System", f"Error: {e}")
            self.update_status("Error")
        finally:
            self.processing = False
            self.stop_btn.config(state="disabled")
            self.finalize_tool_group()

    def _convert_messages_for_anthropic(self):
        anthropic_messages = []
        for msg in self.messages:
            if msg["role"] == "user":
                anthropic_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                if isinstance(msg.get("content"), list):
                    anthropic_messages.append({"role": "assistant", "content": msg["content"]})
                else:
                    anthropic_messages.append({"role": "assistant", "content": msg["content"]})
        return anthropic_messages

    def on_close(self):
        self.stop_event.set()
        if self.current_chat_id:
            save_chat_messages(self.current_chat_id, self.messages)
        for client in self.clients.values():
            try:
                client.close()
            except:
                pass
        self.root.destroy()

if __name__ == "__main__":
    root = ttkb.Window(themename="darkly")
    app = MCPGuiApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
