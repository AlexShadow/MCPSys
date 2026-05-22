# MCPSys — AI‑управление Debian через MCP

MCPSys (MCP System) — это бесплатный графический клиент для управления серверами Debian с помощью искусственного интеллекта. Программа позволяет **администрировать сервер на естественном языке**, используя DeepSeek, OpenAI, Anthropic Claude и другие LLM.

Вам больше не нужно помнить сотни консольных команд — просто опишите задачу, и ИИ выполнит её.
<img width="854" height="582" alt="Setting" src="https://github.com/user-attachments/assets/f486514f-c75c-4e1f-967e-8419d54a740c" />
<img width="854" height="582" alt="Connect" src="https://github.com/user-attachments/assets/ee6f5e89-ff63-4607-9cc7-ef7c3d208bc6" />


## 🚀 Возможности

- **199+ встроенных инструментов** для управления Debian: пакеты, службы, сеть, пользователи, Docker, базы данных, веб‑серверы, безопасность и многое другое.
- **Единый бинарник сервера** на Rust — не требует Python или других зависимостей.
- **Автоустановка сервера** на удалённый Debian одной кнопкой (через SFTP).
- **Поддержка разных AI‑провайдеров**:
  - DeepSeek (V4 Pro, Chat, Reasoner)
  - OpenAI (GPT‑4o, GPT‑4, GPT‑3.5)
  - Anthropic (Claude 3.5 Sonnet, Claude 3 Opus, Haiku)
  - Groq, Together, OpenRouter, Ollama, Custom (OpenAI‑совместимые)
- **Гибкое управление инструментами**: таблица с поиском, включение/отключение отдельных команд.
- **Тёмная тема** и удобный многострочный ввод.
- **Сохранение настроек** (API‑ключ, SSH‑доступ, отключённые инструменты) в `config.json`.
- **Работа без консоли** — можно собрать в один EXE‑файл для Windows.

## 📦 Архитектура
[GUI-клиент на Windows (Python/tkinter)]
│ SSH (stdio)
▼
[Rust-сервер на Debian (mcp-server)]
│ читает tools.toml
▼
[DeepSeek / OpenAI / Claude API]

- **Клиент** (`mcp_gui.py`) — графическое приложение на Python с использованием `ttkbootstrap`.
- **Сервер** (`mcp-server`) — бинарник на Rust, реализующий JSON‑RPC по стандарту Model Context Protocol (MCP).
- **Инструменты** (`tools.toml`) — конфигурационный файл с описанием более 300 команд, разделённых по категориям.

## 🖥️ Быстрый старт (для конечного пользователя)

1. Скачайте `MCPSys.exe` из [релизов](https://github.com/yourname/MCPSys/releases).
2. Запустите EXE, откройте **Settings → AI Provider**:
   - Выберите провайдера (DeepSeek, OpenAI и т.д.).
   - Вставьте API‑ключ.
   - Выберите модель.
3. Перейдите на вкладку **SSH Connection**:
   - Введите IP‑адрес Debian, имя пользователя (`root`) и путь к приватному SSH‑ключу.
   - Нажмите **Install Server on Debian** и введите пароль.
   - Сервер автоматически загрузится на хост.
4. Нажмите **Save** — клиент подключится к серверу и загрузит все доступные инструменты.
5. Начинайте чат: «Покажи загрузку процессора», «Установи Nginx», «Создай пользователя devuser».

## 🔧 Установка и сборка для разработчиков

### Клиент (Windows)

```bash
git clone https://github.com/MCPSys/MCPSys.git
cd MCPSys
pip install -r requirements.txt   # openai, ttkbootstrap, httpx, paramiko, anthropic
python mcp_gui.py
pyinstaller --onefile --noconsole --add-binary "mcp-server;." --add-binary "tools.toml;." mcp_gui.py
```
Сборка в EXE
```bash
pyinstaller --onefile --noconsole --add-binary "mcp-server;." --add-binary "tools.toml;." mcp_gui.py
```
Сервер (Rust, собирается на Debian)
```bash
cd mcp-server-rust
cargo build --release
```
# Бинарник: target/release/mcp-server
tools.toml
Файл с описанием инструментов лежит в /opt/mcp-server/tools.toml на сервере. Его можно редактировать вручную для добавления новых команд.

📚 Примеры команд
Запрос в чате	Действие
«Выведи аптайм и использование памяти»	uptime и free -h
«Обнови все пакеты»	apt update && apt upgrade -y
«Создай базу данных myapp в PostgreSQL»	postgres_create_db
«Перезапусти Nginx»	systemctl restart nginx
«Покажи логи systemd за последние 50 строк»	journalctl -n 50
«Напиши и запусти скрипт для бэкапа /etc»	ИИ напишет код, создаст файл и выполнит его
🛠️ Технологии
Клиент: Python 3.10+, tkinter, ttkbootstrap, openai, anthropic, httpx, paramiko

Сервер: Rust, serde, serde_json, toml

Протокол: JSON‑RPC 2.0 (MCP)

📄 Лицензия
MIT License — свободное использование, модификация и распространение.

🤝 Благодарности
Спасибо DeepSeek за предоставленный API для тестов, сообществу MCP за открытый протокол и всем, кто помогает делать Linux доступнее.
