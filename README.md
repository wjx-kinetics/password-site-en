# Password Vault Keeper

[한국어 (Korean repository)](https://github.com/SLA3DP/password-site) | **English**

A website that works out how long your current password would survive an attack, and then makes a safe one you can use instead. It is built with Python (Flask) and served over HTTPS.

| Weak password | Strong password | Generating a password |
|---|---|---|
| ![Checking a weak password](docs/screenshot-weak.jpg) | ![Checking a strong password](docs/screenshot-strong.jpg) | ![Password generator](docs/screenshot-generate.jpg) |

## Presentation

- [Presentation slides (PDF)](docs/presentation-en.pdf)
- The Korean version is in the [Korean repository](https://github.com/SLA3DP/password-site).

## Why we made it

Password leaks keep happening, but it is hard to feel how weak your own password really is. A password such as `qwer1234!` follows the usual rule of "8 or more characters with a symbol" and is still cracked in under a second. This site turns that fact into a time you can read: years, days, hours, minutes and seconds.

## Features

**Checking a password**
- Shows the time to crack it as you type, in years, days, hours, minutes and seconds.
- Explains why it is weak: a leaked password, a keyboard pattern, a date, a repeat, a dictionary word, and so on.
- Catches Korean habits too. For example it recognizes `dkssud` (안녕, "hello") and `tkfkdgo` (사랑해, "I love you"), which are Korean words typed with the keyboard left in English mode.
- Shows the time for four different kinds of attack.

**Generating a password**
- Length from 8 to 64 characters, with your choice of lowercase, uppercase, numbers and symbols.
- Can leave out look-alike characters such as `0` and `O`, or `l` and `1`.
- Shows how long the new password would last against the same attack.

## How to run it

You need Python 3.9 or later. If you do not have it, install it from [python.org](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH** on the first screen of the installer.

### 1. Download

Press the green **Code** button at the top of this page, choose **Download ZIP**, and unzip it. If you use git:

```
git clone https://github.com/SLA3DP/password-site-en.git
```

### 2. Run

**Windows**: double-click `run.bat` in the folder.

**macOS / Linux**: open Terminal, go to the folder, and run:

```
sh run.sh
```

The first run takes about a minute because it installs the packages it needs. When it is ready, your browser opens `https://localhost:8443` automatically.

### 3. Get past the browser warning

The site uses a certificate it creates itself (a self-signed certificate), so the browser shows a warning such as "Your connection is not private" the first time. Choose **Advanced → Proceed to localhost (unsafe)**. The connection is still encrypted.

### Stopping it

Press `Ctrl + C` in the terminal window where it is running, or close that window.

### Options

| Command | What it does |
|---|---|
| `run.bat --lan` / `sh run.sh --lan` | Lets phones and other computers on the same Wi-Fi connect. |
| `--port 9000` | Uses another port instead of 8443. |
| `--no-browser` | Does not open the browser automatically. |

### Running it without the scripts

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      (Windows)
.venv/bin/pip install -r requirements.txt          (macOS / Linux)
.venv\Scripts\python app.py                        (Windows)
.venv/bin/python app.py                            (macOS / Linux)
```

## How it works

### How the crack time is calculated

```
time = guesses the attacker needs ÷ guesses per second
```

**Estimating the guesses**

Attackers do not try every combination from the start. They begin with what people use most: leaked passwords, dictionary words, keyboard patterns and dates. Counting only the length and the kinds of characters makes a password look far stronger than it is.

This site uses `zxcvbn`, an algorithm made by Dropbox, to split the password into pieces and estimate how early an attacker would try each one.

| Pattern it finds | Examples |
|---|---|
| Leaked passwords | `password`, `qwer1234` |
| Dictionary words, common names | `summer`, `michael` |
| Character swaps | `P@ssw0rd` |
| Keyboard patterns | `qwerty`, `1q2w3e4r` |
| Sequences and repeats | `abcd`, `1234`, `aaaa` |
| Dates and years | `2024`, `19990101` |
| Korean words (added by us) | `dkssud`, `안녕하세요` |

A random piece that matches no pattern counts as `character types ^ length`. The character types are 26 for lowercase, 26 for uppercase, 10 for digits, 33 for symbols and 2350 for Korean letters, adding only the kinds that appear.

**Guesses per second**

The same password lasts very differently depending on the attack. The large clock on the site uses the last row, the worst case.

| Attack | Speed |
|---|---|
| Guessing at a login page (rate-limited) | 100 per hour |
| Guessing at a login page (no limit) | 10 per second |
| Leaked database, slow hash (bcrypt) | 10,000 per second |
| Leaked database, fast hash (MD5, SHA-1) | 10 billion per second |

**Verdicts** (at 10 billion guesses per second)

| Time to crack | Verdict |
|---|---|
| Under 1 minute | Cracked instantly |
| Under 1 day | Very weak |
| Under 1 year | Weak |
| Under 100 years | Fair |
| 100 years or more | Strong |

### How a password is generated

It uses the `secrets` module from the Python standard library. Ordinary random numbers (`random`) can be predicted, so they must not be used for passwords. `secrets` uses cryptographic randomness from the operating system. To make sure each chosen kind of character appears at least once, the password is drawn again until it does.

Randomness is shown as `length × log2(character types)` bits. The default setting (20 characters from 81 types) is about 127 bits.

### Structure

```
Browser (static/)                      Python server (app.py)
┌──────────────────────┐   HTTPS    ┌─────────────────────────────┐
│ Input box and clock  │ ─────────> │ /api/check     check a password │
│ Only draws results   │ <───────── │ /api/generate  make a password  │
└──────────────────────┘    JSON    └─────────────────────────────┘
```

The Python server does all the calculation. The JavaScript in the browser only draws the results it receives.

### What we did for security

- **HTTPS**: the certificate is created automatically on the first run and kept in the `certs/` folder. Passwords are never sent unencrypted.
- **Nothing is stored**: a password is used only for the calculation and is not written to any file or log.
- **No outside requests**: no fonts or scripts are loaded from other servers. A security header (CSP) also blocks outside code.
- **Rate limit**: one person is blocked for a while after more than 150 requests in 10 seconds.
- **Local only by default**: other devices cannot connect unless you add the `--lan` option.

## Files

| File | Role |
|---|---|
| `app.py` | The Python server: checking, time calculation, password generation, HTTPS certificate |
| `static/index.html` | Page layout and text |
| `static/style.css` | Colors and shapes |
| `static/app.js` | Sends requests to the server and shows the results |
| `requirements.txt` | The Python packages it needs |
| `run.bat`, `run.sh` | Start scripts for Windows and for macOS / Linux |

## Built with

- Python 3, Flask (web server)
- zxcvbn (password pattern analysis)
- cryptography (HTTPS certificate)
- HTML, CSS, JavaScript (the page)

## Things to know

- The times are estimates. Real attack speed depends on how a site stores passwords and on the attacker's hardware.
- When you run it on your own computer, your password never leaves that computer. If you open an address run by someone else, do not type a password you really use. Try an example of a similar shape instead.

## Made by

Jang WonJoon ∙ Seoul Robotics High School · [github.com/SLA3DP](https://github.com/SLA3DP)
