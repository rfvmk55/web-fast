# Web-Fast · BaBaTa

> 把 sqlmap、commix、dirsearch、ffuf、nuclei 这些命令行工具收进一个终端窗口里。
> 不用 cd、不用敲 `python xxx.py`、不用背参数。

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)
![Deps](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)

---

## 它解决什么问题

| 原来的样子 | 用 Web-Fast |
|---|---|
| 每次打开都得先 `cd` 到工具目录 | 点一下工具名，自动切目录 |
| 得记住入口是 `sqlmap.py` 还是 `dirsearch.py` | 自动填好 `python sqlmap.py `，光标停在后面 |
| 参数靠背，`--level`、`--tamper` 各是什么全靠猜 | 敲 `-` 出候选，每个参数带中文说明和示例 |
| 打错一个字母白跑十分钟 | 参数名校验 + 候选补全 |
| 输出刷屏、进度条几百行、结果和日志糊成一团 | 进度折叠成一行、结果按状态码上色、`Ctrl+F` 搜索 |
| 想同时跑两个扫描得开两个终端 | 多标签，一个工具一个标签 |

---

## 特性

### 参数候选（inline，不是弹窗）

在输入框里敲 `-`，候选条直接浮在输入框上方：

```text
┌────────────────────────────────────────────────────┐
│ ▸ -r            从文件加载 HTTP 请求                │
│   --risk        风险等级（1-3）                     │
│   --tamper      混淆脚本，绕过 WAF                  │
│   -u            目标 URL                            │
│   3 项  Tab 选中 · ↑↓ 切换 · Esc 关闭               │
├────────────────────────────────────────────────────┤
│ PS C:\tools\sqlmap-dev> python sqlmap.py -          │
└────────────────────────────────────────────────────┘
```

- `Tab` 选中，`↑↓` 切换，`Esc` 关掉
- 输入 `-l` 会收到 `--level`，`-r`、`-u` 排在最前

### 值候选

参数后面按空格，自动弹该参数的可选值：

| 参数 | 弹出什么 |
|---|---|
| `-r` | txt 目录下的文件列表 + 「浏览文件…」 |
| `--tamper` | 84 个 tamper 脚本 |
| `-e` | 26 个扩展名（php/html/asp/zip…） |
| `--exclude-status` | 常见状态码列表 |
| `--technique` | B/E/U/S/T/Q/BEUST |

**多值参数支持逗号续选**：

```text
-e php,      → 候选条再弹一次
-e php,html,
-e php,html,js
```

选过的不会重复追加。

### 引号按参数决定

不是所有参数都该加引号。每个参数在 TOML 里配了 `quote` 规则：

```toml
[[param]]
name = "-u"
quote = "1"        # 强制加引号 → -u "http://..."

[[param]]
name = "-e"
quote = "0"        # 不加引号   → -e php,html

[[param]]
name = "--level"
# 不写 = 自动判断：路径类加引号，其余看值里有没有空格
```

### 输出按状态码上色

```text
[23:20:59] 403 -   321B - /cgi-bin/          ← 4xx 灰蓝
[23:21:10] 200 -     2B - /health            ← 2xx 绿色
[23:21:12] 200 -     2K - /index.php
[23:21:28] 301 -     0B - /admin  →  /admin/ ← 3xx 橙色
[23:21:41] 200 -     6K - /www.zip           ← 大小黄色、路径蓝色
[23:22:01] 500 -     3K - /api/debug         ← 5xx 红色
```

时间戳青色、状态码按首位分色、大小黄色、路径蓝色。同时解析 ANSI 转义序列，工具自己输出颜色也能渲染。

### 进度条折叠，不刷屏

dirsearch 在管道模式下的进度帧没有任何分隔符，几百帧会连成一整行。Web-Fast 识别这种帧序列，把整串折叠成一条状态：

```text
[● dirsearch  57%  5561/9631  ×]
```

进度显示在标签页标题上，终端里只留结果行。

### 多标签

左边点一个工具 = 开一个标签，每个标签独立：

- 自己的工作目录
- 自己的输入内容
- 自己的输出流
- 自己的运行状态

dirsearch 扫着，切到另一个标签跑 sqlmap，互不干扰。

### Ctrl+F 查找

```text
🔍 [www.zip                    ]  1/1   ↑  ↓  ×
```

- 输入即高亮，所有命中行标黄底
- `Enter` 下一个 / `Shift+Enter` 上一个
- `Esc` 关闭
- 只搜当前标签

### 每个工具独立设置

点「设置」→ 左边选工具 → 右边改这个工具的参数路径：

```text
工具根目录  root
[C:\tools\sqlmap-dev                    ]  [浏览…]
[打开]

请求文件目录  txt_dir
[txt                                       ]  [浏览…]
✓ 目录存在

输出目录  output_dir
[output                                    ]  [浏览…]
✓ 目录存在
```

- 「浏览…」弹系统文件夹选择器
- 「打开」在资源管理器里打开
- 子目录填相对路径（如 `txt`）会跟着工具根目录走
- 「自动扫描本机」自动找常见安装位置

### 路径换电脑能用

配置里的 `C:/Users/旧用户名/...` 会自动映射到当前用户。也可以设环境变量临时覆盖：`WEBFAST_SQLMAP`。

---

## 快速开始

### 环境

- Windows 10 / 11
- Python 3.9+
- WebView2 运行时（Win11 自带；Win10 大多数有，没有就装一次 [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/)）

### 安装

```powershell
git clone https://github.com/<your-name>/web-fast.git
cd web-fast

python -m pip install -r requirements.txt
```

`requirements.txt` 只有一行（`pywebview`），其余全用标准库。

### 准备工具本体

Web-Fast **不附带**任何工具，需要自己下载：

| 工具 | 下载 |
|---|---|
| sqlmap | https://github.com/sqlmapproject/sqlmap |
| commix | https://github.com/commixproject/commix |
| dirsearch | https://github.com/maurosoria/dirsearch |
| ffuf | https://github.com/ffuf/ffuf |
| nuclei | https://github.com/projectdiscovery/nuclei |

放哪都行，Web-Fast 只要知道路径。

### 运行

```powershell
# 桌面应用（独立窗口，推荐）
python webfast.py app

# 浏览器模式
python webfast.py web

# 指定端口 / 不自动开浏览器
python webfast.py web -p 9000 --no-browser
```

首次打开点「设置」→「自动扫描本机」，或者手动填工具根目录。

### 命令行也能用

```powershell
python webfast.py list                    # 列出所有工具
python webfast.py info sqlmap             # 看 sqlmap 的参数表
python webfast.py search tamper           # 跨工具搜参数
python webfast.py run sqlmap -u http://t/ --batch
python webfast.py discover                # 扫本机安装的工具
python webfast.py doctor                  # 自检
```

---

## 界面

![主界面](docs/images/main.png)

![参数候选](docs/images/picker.png)

### 快捷键

| 按键 | 作用 |
|---|---|
| `-` | 弹参数候选 |
| 空格 | 参数有候选值时弹值候选 |
| `Tab` | 选中当前候选 |
| `↑ ↓` | 候选间切换，无候选时翻历史 |
| `Esc` | 关闭候选 / 关闭查找 |
| `Enter` | 执行 / 运行中发送到工具 stdin |
| `Ctrl+C` | 结束当前命令 |
| `Ctrl+F` | 在输出里查找 |
| `Ctrl+空格` | 强制弹候选 |

---

## 添加自己的工具

新工具的接入只需要一个 TOML 文件，不用改代码。

```toml
# tools/mytool.toml
id = "mytool"
name = "mytool"
category = "侦察"
summary = "一句话说明"
cwd = "third_party/mytool"          # 相对项目根，或绝对路径
runner = "python"                    # python | module | direct
entry = "mytool.py"
requires = ["requests"]

[[param]]
name = "-u"
type = "string"
label = "目标地址"
desc = "要测试的 URL"
example = "-u http://target/"
quote = "1"

[[param]]
name = "-w"
type = "file"
label = "字典"
desc = "要用的字典文件"
source = "glob:" + D + "{dict_dir}/*.txt"
setting = "dict_dir"

[[setting]]
key = "dict_dir"
label = "字典目录"
default = "db"
type = "dir"

[[template]]
name = "快速扫描"
cmd = "-u " + D + "{url} -w " + D + "{dict_dir}/common.txt"
```

字段说明：

| 字段 | 作用 |
|---|---|
| `type` | `bool` / `string` / `file` / `dir` / `positional` |
| `quote` | `"1"` 强制加引号、`"0"` 不加、不写自动判断 |
| `source` | 候选来源：`list:a\|b\|c` / `glob:路径` / `dir:路径` |
| `source_multi` | `true` 时支持逗号续选 |
| `repeat` | `true` 时参数可重复出现 |

放好 TOML，重启应用，左侧就多一个工具。

---

## 打包成 exe

```powershell
python -m PyInstaller --noconfirm --onedir --windowed --name WebFast ^
  --icon "web\icon.ico" ^
  --add-data "web;web" ^
  --add-data "tools;tools" ^
  --add-data "settings.toml;." ^
  --collect-all webview ^
  --hidden-import clr ^
  webfast_app.py
```

产物在 `dist/WebFast/`，整个文件夹拷走就能用，目标机器不需要装 Python。

| 参数 | 作用 |
|---|---|
| `--windowed` | 不弹控制台黑框 |
| `--onedir` | 目录版，启动快（单文件版每次要解压） |
| `--add-data` | 把 `web/`、`tools/`、配置打进包 |
| `--collect-all webview` | pywebview 的 JS/DLL 资源全收 |
| `--hidden-import clr` | pythonnet，WebView2 靠它 |

### 打包版的路径分两层

```python
APP_ROOT  = _MEIPASS 或项目根    # 只读资源（web/、tools/）
USER_ROOT = exe 所在目录          # 可写（local_paths.toml、output/）
```

打包后 `sys.executable` 指向 exe 自己，不能拿它跑工具脚本，所以单独做了解析：

```python
def python_exe() -> str:
    if not _is_frozen():
        return sys.executable          # 源码模式
    for name in ("python.exe", "python3.exe", "python"):
        found = shutil.which(name)     # 打包后找系统 Python
        if found:
            return found
    return shutil.which("py.exe") or "python"
```

---

## 项目结构

```text
web-fast/
├── webfast/
│   ├── registry.py      工具与参数的模型、路径解析
│   ├── launcher.py      进程启动、输出泵、进度帧识别
│   ├── server.py        HTTP + SSE 服务
│   ├── resolve.py       候选值解析（文件/目录/枚举）
│   ├── discover.py      扫本机安装的工具
│   ├── app.py           桌面窗口（pywebview + DWM 深色标题栏）
│   ├── gui.py           Tkinter 版（备用）
│   └── cli.py           命令行接口
├── web/                 前端（无构建，原生 HTML/CSS/JS）
│   ├── index.html
│   ├── app.js
│   └── style.css
├── tools/               工具描述（TOML，一个工具一个文件）
├── tests/               测试
├── settings.toml        全局配置
└── webfast.py           主入口
```

后端只用标准库：`http.server` + `ThreadingHTTPServer` + SSE，没有 Flask/FastAPI。前端没有打包步骤，改完刷新就生效。

---

## 测试

```powershell
python -m pytest tests/ -v

# 或者单独跑
python tests/test_param.py
python tests/test_web.py
python tests/test_progress.py
```

覆盖：参数解析、候选生成、输出分类、SSE 流、设置读写。

---

## 已知限制

- **只支持 Windows**（依赖 WebView2 和 `taskkill` 杀进程树）
- **工具需要自己装**，Web-Fast 只是外壳
- Python 写的工具需要系统有 Python

---

## 致谢

工具本身来自这些项目：

- [sqlmap](https://github.com/sqlmapproject/sqlmap)
- [commix](https://github.com/commixproject/commix)
- [dirsearch](https://github.com/maurosoria/dirsearch)
- [ffuf](https://github.com/ffuf/ffuf)
- [nuclei](https://github.com/projectdiscovery/nuclei)

界面风格参考了 VS Code 的深色主题和 CyberChef 的配色。

---

## 作者

**parrot**

反馈或改进建议：2571308976@qq.com

## License

MIT
