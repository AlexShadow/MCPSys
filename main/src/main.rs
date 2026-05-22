use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{self, BufRead, Write};
use std::process::Command;

// ----- JSON-RPC структуры -----
#[derive(Deserialize)]
struct Request {
    jsonrpc: String,
    method: String,
    params: Option<serde_json::Value>,
    id: Option<serde_json::Value>,
}

#[derive(Serialize)]
struct Response {
    jsonrpc: String,
    id: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<ErrorBody>,
}

#[derive(Serialize)]
struct ErrorBody {
    code: i32,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<serde_json::Value>,
}

// ----- MCP‑инструмент из tools.toml -----
#[derive(Deserialize, Clone)]
struct ToolConfig {
    name: String,
    description: String,
    command: String,
    #[serde(default)]
    parameters: HashMap<String, ParamDef>,
}

#[derive(Deserialize, Clone)]
struct ParamDef {
    #[serde(rename = "type")]
    param_type: String,
    description: String,
    #[serde(default)]
    required: bool,
}

// ----- Главная программа -----
fn main() -> io::Result<()> {
    // Читаем tools.toml
    let config_path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "/etc/mcp-server/tools.toml".to_string());
    let toml_content = std::fs::read_to_string(&config_path)
        .expect("Cannot read tools.toml");
    let config: TomlConfig = toml::from_str(&toml_content)
        .expect("Invalid tools.toml");
    let tools = config.tools;

    eprintln!("Loaded {} tools from {}", tools.len(), config_path);

    let stdin = io::stdin();
    let mut stdout = io::stdout();

    // Основной цикл обработки запросов
    for line in stdin.lock().lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let request: Request = match serde_json::from_str(&line) {
            Ok(req) => req,
            Err(e) => {
                let err = Response {
                    jsonrpc: "2.0".to_string(),
                    id: None,
                    result: None,
                    error: Some(ErrorBody {
                        code: -32700,
                        message: format!("Parse error: {}", e),
                        data: None,
                    }),
                };
                writeln!(stdout, "{}", serde_json::to_string(&err).unwrap())?;
                stdout.flush()?;
                continue;
            }
        };

        let response = match request.method.as_str() {
            "initialize" => {
                let result = serde_json::json!({
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "Debian Server",
                        "version": "0.1.0"
                    }
                });
                Response {
                    jsonrpc: "2.0".to_string(),
                    id: request.id,
                    result: Some(result),
                    error: None,
                }
            }
            "notifications/initialized" | "initialized" => {
                // Уведомление, ответ не отправляем
                continue;
            }
            "tools/list" => {
                let tools_json: Vec<serde_json::Value> = tools.iter().map(|tool| {
                    let mut properties = serde_json::Map::new();
                    let mut required = Vec::new();
                    for (name, param) in &tool.parameters {
                        properties.insert(name.clone(), serde_json::json!({
                            "type": param.param_type,
                            "description": param.description,
                        }));
                        if param.required {
                            required.push(name.clone());
                        }
                    }
                    serde_json::json!({
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                        }
                    })
                }).collect();
                let result = serde_json::json!({ "tools": tools_json });
                Response {
                    jsonrpc: "2.0".to_string(),
                    id: request.id,
                    result: Some(result),
                    error: None,
                }
            }
            "tools/call" => {
                let params = request.params.unwrap_or(serde_json::Value::Null);
                let tool_name = params["name"].as_str().unwrap_or("").to_string();
                let args = params["arguments"].clone();

                // Ищем инструмент
                let tool = tools.iter().find(|t| t.name == tool_name);
                match tool {
                    None => Response {
                        jsonrpc: "2.0".to_string(),
                        id: request.id,
                        result: None,
                        error: Some(ErrorBody {
                            code: -32602,
                            message: format!("Tool '{}' not found", tool_name),
                            data: None,
                        }),
                    },
                    Some(tool) => {
                        // Подставляем параметры в команду
                        let mut cmd_line = tool.command.clone();
                        if let Some(args_obj) = args.as_object() {
                            for (key, value) in args_obj {
                                let placeholder = format!("{{{}}}", key);
                                let value_str = match value {
                                    serde_json::Value::String(s) => s.clone(),
                                    other => other.to_string(),
                                };
                                cmd_line = cmd_line.replace(&placeholder, &value_str);
                            }
                        }

                        // Выполняем команду
                        let output = Command::new("sh")
                            .arg("-c")
                            .arg(&cmd_line)
                            .output();

                        let text = match output {
                            Ok(out) => String::from_utf8_lossy(&out.stdout).to_string()
                                + String::from_utf8_lossy(&out.stderr).as_ref(),
                            Err(e) => format!("Command failed: {}", e),
                        };

                        let result = serde_json::json!({
                            "content": [
                                {
                                    "type": "text",
                                    "text": text
                                }
                            ]
                        });
                        Response {
                            jsonrpc: "2.0".to_string(),
                            id: request.id,
                            result: Some(result),
                            error: None,
                        }
                    }
                }
            }
            _ => Response {
                jsonrpc: "2.0".to_string(),
                id: request.id,
                result: None,
                error: Some(ErrorBody {
                    code: -32601,
                    message: format!("Method not found: {}", request.method),
                    data: None,
                }),
            },
        };

        // Отправляем ответ (кроме уведомлений)
        writeln!(stdout, "{}", serde_json::to_string(&response).unwrap())?;
        stdout.flush()?;
    }
    Ok(())
}

#[derive(Deserialize)]
struct TomlConfig {
    tools: Vec<ToolConfig>,
}
