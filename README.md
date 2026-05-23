# MCPSys — AI‑администратор Linux через MCP

MCPSys (MCP System) — это бесплатный графический клиент для управления
серверами Linux с помощью искусственного интеллекта. Программа позволяет
**администрировать любую Linux‑систему на естественном языке**,
используя DeepSeek, OpenAI, Anthropic Claude и другие LLM.

![Settings](https://github.com/user-attachments/assets/f486514f-c75c-4e1f-967e-8419d54a740c)
![Connect](https://github.com/user-attachments/assets/ee6f5e89-ff63-4607-9cc7-ef7c3d208bc6)

Вам больше не нужно помнить сотни консольных команд — просто опишите задачу,
и ИИ выполнит её на вашем сервере.

## 🚀 Возможности

- **476+ кроссплатформенных инструментов** — автоматически определяют
  пакетный менеджер (apt/dnf/pacman/apk/zypper), систему инициализации
  (systemd/openrc/sysv) и фаервол (ufw/firewalld/nft/iptables).
  Работают на **Debian, Ubuntu, Fedora, Arch, Alpine, openSUSE** и других.
- **Единый бинарник сервера** на Rust — не требует Python или других зависимостей.
- **Автоустановка сервера** на удалённый Linux одной кнопкой (через SFTP).
- **Поддержка разных AI‑провайдеров**:
  - DeepSeek (V4 Pro, Chat, Reasoner)
  - OpenAI (GPT‑4o, GPT‑4, GPT‑3.5)
  - Anthropic (Claude 3.5 Sonnet, Claude 3 Opus, Haiku)
  - Groq, Together, OpenRouter, Ollama, Custom (OpenAI‑совместимые, локальные LLM)
- **Множественные серверы** — одновременное подключение к нескольким машинам,
  AI видит их все и может выполнять кросс‑серверные команды.
- **Гибкое управление инструментами**: таблица с поиском, включение/отключение
  отдельных команд с защитой от вызова отключённых инструментов.
- **Тёмная тема**, многострочный ввод, контекстное меню (правая кнопка мыши).
- **Сворачиваемые блоки команд** — не засоряют чат, раскрываются по клику.
- **Сохранение и переключение чатов**, переименование, экспорт в JSON.
- **Автосохранение** истории после каждого сообщения.
- **Кнопка Stop** для прерывания генерации.
- **Автоматическое переподключение** при обрыве SSH.
- **Сохранение настроек** (API‑ключ, SSH‑доступ, отключённые инструменты)
  в `config.json`.
- **Кроссплатформенный GUI‑клиент** — работает на Windows, Linux, macOS.
- **Портативные сборки**: EXE для Windows, AppImage для Linux.

## 📦 Архитектура
[GUI-клиент (Python/tkinter)]
│ SSH (stdio)
▼
[Rust-сервер на Linux (mcp-server)]
│ читает tools.toml
▼
[DeepSeek / OpenAI / Claude / локальный LLM]


- **Клиент** (`mcp_gui.py`) — графическое приложение на Python с `ttkbootstrap`.
- **Сервер** (`mcp-server`) — бинарник на Rust, реализующий JSON‑RPC
  по стандарту Model Context Protocol (MCP).
- **Инструменты** (`tools.toml`) — конфигурационный файл с 476+ командами,
  покрывающими все основные дистрибутивы Linux.

## 🖥️ Быстрый старт

1. Скачайте последнюю версию под вашу ОС из [релизов](https://github.com/AlexShadow/MCPSys/releases):
   - **Windows**: `MCPSys.exe`
   - **Linux**: `MCPSys.AppImage`
2. Запустите программу, откройте **Settings → AI Provider**:
   - Выберите провайдера.
   - Вставьте API‑ключ.
   - Выберите модель.
3. Перейдите на вкладку **Servers**:
   - Введите IP‑адрес сервера, порт, имя пользователя и путь к SSH‑ключу.
   - Нажмите **Install Server on Debian** (или **Check Server**,
     если сервер уже установлен).
4. Нажмите **Save** — клиент подключится и загрузит все доступные инструменты.
5. Начинайте чат: «Покажи загрузку процессора», «Установи Nginx»,
   «Создай пользователя devuser».

## 🔧 Установка и сборка для разработчиков

### Зависимости

```bash
pip install -r requirements.txt
```
Сборка EXE (Windows)

```
pyinstaller --onefile --noconsole --name MCPSys `
    --add-binary "mcp-server;." --add-binary "tools.toml;." `
    --collect-all paramiko --collect-all anthropic `
    mcp_gui.py
```
Сборка AppImage (Linux)
```
pip install pyinstaller paramiko anthropic openai ttkbootstrap httpx
pyinstaller --onefile --name MCPSys \
    --add-binary "mcp-server:." --add-binary "tools.toml:." \
    --collect-all paramiko --collect-all anthropic \
    mcp_gui.py
# Выходной файл: dist/MCPSys — можно переименовать в MCPSys.AppImage
```
Сервер можно установить вручную в /opt/mcp-server/, либо через кнопку
«Install Server on Debian» в GUI.

## 📚 Примеры команд

| Запрос в чате                                   | Действие                                                                 |
| :---------------------------------------------- | :------------------------------------------------------------------------ |
| «Покажи загрузку процессора»                    | `uptime` и `lscpu`                                                        |
| «Сколько свободного места на дисках?»           | `df -h`                                                                   |
| «Обнови все пакеты»                             | `upgrade_system` (автоопределение пакетного менеджера)                    |
| «Установи htop»                                 | `install_package htop`                                                    |
| «Перезапусти nginx»                             | `service_restart nginx` (systemd / openrc / sysv)                         |
| «Открой порт 443»                               | `firewall_allow_port 443` (ufw / firewalld / nft / iptables)              |
| «Создай пользователя devuser»                   | `useradd devuser`                                                         |
| «Добавь задачу в cron: бэкап каждую ночь»       | `cron_add "0 3 * * * tar -czf /backup/etc.tar.gz /etc"`                  |
| «Покажи логи systemd за последние 50 строк»     | `journalctl -n 50`                                                        |
| «Какие контейнеры Docker запущены?»              | `docker ps`                                                               |
| «Скопируй файл с сервера A на сервер B»         | `rsync` между серверами                                                   |
| «Напиши и запусти скрипт для бэкапа /etc»       | ИИ напишет bash-скрипт, создаст файл и выполнит его                       |
| «Проверь, какие порты открыты»                  | `netstat -tulpn` или `ss -tulpn`                                          |
| «Какой внешний IP у сервера?»                   | `curl ifconfig.me`                                                        |


🛠️ Технологии
Клиент: Python 3.10+, tkinter, ttkbootstrap, openai, anthropic, httpx, paramiko

Сервер: Rust, serde, serde_json, toml

Протокол: JSON‑RPC 2.0 (MCP)

📄 Лицензия
MIT License — свободное использование, модификация и распространение.

🤝 Благодарности
Спасибо DeepSeek за предоставленный API для тестов, сообществу MCP
за открытый протокол и всем, кто помогает делать Linux доступнее.
