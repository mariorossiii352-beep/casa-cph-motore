"""Accesso a Facebook dal PC, da lanciare a mano. Serve una volta sola.

Apre il normale Google Chrome con un profilo nuovo e vuoto (non un browser da
automazione, cosi' il reCAPTCHA funziona). Entri in Facebook; appena l'accesso e'
completo il programma:
  1. prende i cookie della sessione (in un formato che funziona anche su Linux);
  2. crea una chiave casuale nuova e la salva nei segreti del repository GitHub
     (la chiave non viene mai scritta su disco ne' mostrata);
  3. cifra i cookie con quella chiave e carica il file cifrato su GitHub.

Uso:  python accesso_pc.py
"""
import json, os, secrets, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = "mariorossiii352-beep/casa-cph-motore"
GH = r"C:\Users\danie\tools\gh\bin\gh.exe"
OPENSSL = r"C:\Program Files\Git\usr\bin\openssl.exe"
CHROME = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
PORTA = 9333


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


lavoro = Path(tempfile.mkdtemp(prefix="casa-cph-accesso-"))
chrome = subprocess.Popen([CHROME, f"--user-data-dir={lavoro / 'chrome'}", f"--remote-debugging-port={PORTA}",
                           "--no-first-run", "--no-default-browser-check", "https://www.facebook.com/"])
try:
    time.sleep(4)
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORTA}")
        ctx = browser.contexts[0]
        log("Entra in Facebook nella finestra di Chrome che si e' aperta (hai 20 minuti).")
        fine = time.time() + 20 * 60
        collegato = lambda: any(c["name"] == "c_user" for c in ctx.cookies("https://www.facebook.com"))
        while time.time() < fine and not collegato():
            time.sleep(5)
        if not collegato():
            log("Accesso non completato. Rilancia il programma quando vuoi.")
            sys.exit(1)
        log("Accesso riuscito. Aspetto un minuto che Facebook finisca di caricare, non chiudere Chrome.")
        time.sleep(60)
        stato = {"cookies": [c for c in ctx.cookies() if "facebook.com" in c["domain"]], "origins": []}
        browser.close()

    chiave = secrets.token_urlsafe(48)
    env = dict(os.environ, PROFILO_KEY=chiave)
    cifrato = lavoro / "sessione.enc"
    subprocess.run([OPENSSL, "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-pass", "env:PROFILO_KEY",
                    "-out", str(cifrato)], input=json.dumps(stato).encode(), env=env, check=True)
    del stato

    log("Salvo la chiave nei segreti di GitHub...")
    subprocess.run([GH, "secret", "set", "PROFILO_KEY", "-R", REPO], input=chiave.encode(), check=True,
                   stdout=subprocess.DEVNULL)
    del chiave, env

    log("Carico la sessione cifrata su GitHub...")
    esiste = subprocess.run([GH, "release", "view", "sessione", "-R", REPO],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not esiste:
        subprocess.run([GH, "release", "create", "sessione", "-R", REPO, "--title", "sessione",
                        "--notes", "File cifrato usato dal motore. Non contiene dati leggibili."],
                       check=True, stdout=subprocess.DEVNULL)
    subprocess.run([GH, "release", "upload", "sessione", str(cifrato), "--clobber", "-R", REPO],
                   check=True, stdout=subprocess.DEVNULL)
    log("FATTO. Il motore su GitHub usera' questa sessione.")
finally:
    chrome.terminate()
    time.sleep(2)
    shutil.rmtree(lavoro, ignore_errors=True)
