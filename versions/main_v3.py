# main_v4.py
# pip install selenium webdriver-manager
# Python >= 3.9 (usa zoneinfo)

import os, re, time, random, unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# =========================
# CONFIG
# =========================
NOME_DO_GRUPO = "Bot Test"       # nome EXATO do grupo
SECAO_DA_LISTA = "Volta"         # "Volta" ou "Ida"
NOME_PARA_ADICIONAR = "Hélio"    # seu nome (use "Helio" se preferir sem acento)

TZ = ZoneInfo("America/Campo_Grande")
HORA_INICIO_PREPARACAO = 20
MINUTO_INICIO_PREPARACAO = 0
HORA_INICIO_VIGILANCIA = 21
HORA_FIM_VIGILANCIA = 23

SEND_MESSAGES = False            # valide primeiro no console
MENSAGEM_FALLBACK = "Boa noite! (fallback) Lista atualizada conforme combinado."

ZWSP = "\u200B"  # Zero Width Space — impede auto-lista do WhatsApp

# =========================
# NORMALIZAÇÃO / HELPERS
# =========================
def _normalize(s: str) -> str:
    if not s: return ""
    s = s.replace("\u2060", " ")
    return "\n".join([re.sub(r"\s+$", "", line) for line in s.splitlines()])

def _strip_accents_lower(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s or "")
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower()

def _split_nonempty_lines(text):
    # mantém ordem, remove somente linhas 100% vazias
    return [ln.strip() for ln in text.splitlines() if ln is not None and ln.strip() != ""]

def _collapse_tail_repeat(text):
    """
    Remove repetição no RODAPÉ: se o final é B+B (dois blocos idênticos consecutivos),
    corta o último. Verifica no fim, não só no começo.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln is not None]
    n = len(lines)
    for m in range(1, n // 2 + 1):
        tail1 = [x.strip() for x in lines[n-2*m:n-m]]
        tail2 = [x.strip() for x in lines[n-m:n]]
        if tail1 == tail2 and m >= 2:  # exige pelo menos 2 linhas para evitar falso-positivo
            return "\n".join(lines[:n-m]).strip()
    return "\n".join(lines).strip()

def _is_section_title(line: str) -> bool:
    norm = _strip_accents_lower((line or "").strip())
    return ("ida" in norm) or ("volta" in norm)

def _visible_number_from_line(line: str):
    m = re.match(r"^\s*(\d+)\.\s*(.*)$", line or "")
    if m:
        return int(m.group(1)), (m.group(2) or "").strip()
    return None, (line or "").strip()

def _escape_autolist_numbered(n: int, text: str) -> str:
    # 1.<ZWSP> espaço + texto -> não ativa auto-lista
    return f"{n}.{ZWSP} {text}"

# =========================
# PARSER FLEX + RENUMERAÇÃO
# =========================
def parse_sections_flex(msg: str):
    """
    - Header: tudo até o 1º título contendo 'Ida' ou 'Volta'
    - Seções: título = linha com 'Ida' ou 'Volta'; itens = linhas não-vazias
      até o próximo título ou fim (com ou sem numeração original)
    """
    msg = _normalize(msg)
    lines = [ln for ln in msg.splitlines()]

    header_lines, sections = [], []
    i = 0
    while i < len(lines) and not _is_section_title(lines[i]):
        header_lines.append(lines[i]); i += 1

    current = None
    while i < len(lines):
        ln = (lines[i] or "").strip()
        if not ln:
            i += 1; continue
        if _is_section_title(ln):
            current = {"title": ln, "items": []}
            sections.append(current)
        else:
            if current:
                current["items"].append(ln)
        i += 1

    return {"header": "\n".join(header_lines).strip(), "sections": sections, "footer": ""}

def add_name_continue_count(struct, section_key: str, nome: str):
    key_norm = _strip_accents_lower(section_key)
    nome_norm = _strip_accents_lower(nome)
    for sec in struct["sections"]:
        if _strip_accents_lower(sec["title"]).startswith(key_norm):
            texts = [_visible_number_from_line(x)[1] for x in sec["items"]]
            if any(_strip_accents_lower(t) == nome_norm for t in texts):
                return True
            sec["items"].append(nome)
            return True
    return False

def rebuild_with_numbering(struct):
    out = []
    if struct["header"]:
        out.append(struct["header"])
        out.append("")

    for sec in struct["sections"]:
        out.append(sec["title"])
        # remove qualquer numeração existente e renumera limpo
        item_texts = [_visible_number_from_line(x)[1] for x in sec["items"]]
        for idx, t in enumerate(item_texts, start=1):
            out.append(_escape_autolist_numbered(idx, t))
        out.append("")

    texto = "\n".join(out)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    return texto

# =========================
# WEBDRIVER / WHATSAPP
# =========================
def inicializar_driver_stealth():
    try:
        options = webdriver.ChromeOptions()
        data_dir = os.path.abspath("./whatsapp_session_data")
        os.makedirs(data_dir, exist_ok=True)
        options.add_argument(f"--user-data-dir={data_dir}")
        options.add_argument("--profile-directory=Default")

        options.add_argument("--log-level=3")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.maximize_window()
        return driver
    except Exception as e:
        print(f"Erro ao iniciar o Chrome Driver com webdriver-manager: {e}")
        return None

def abrir_whatsapp_web(driver, timeout=90):
    driver.get("https://web.whatsapp.com/")
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div#app"))
    )
    print("WhatsApp Web carregado.")

def abrir_grupo(driver, nome_grupo, timeout=25):
    try:
        xp = f"//span[@dir='auto' and @title='{nome_grupo}']"
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
        el.click()
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div#main")))
        return True
    except TimeoutException:
        print(f"Não achei '{nome_grupo}' na lateral. Confirme o nome exato (título do span).")
        return False

def obter_texto_ultima_mensagem_preciso(driver):
    """
    Extrai a ÚLTIMA bolha de mensagem, normaliza e remove duplicação no RODAPÉ.
    """
    try:
        base = driver.find_elements(By.XPATH, "(//div[contains(@class,'message-in') or contains(@class,'message-out')])[last()]")
        if not base:
            base = driver.find_elements(By.XPATH, "(//div[@role='row'])[last()]")
        if not base:
            return ""

        spans = base[-1].find_elements(By.XPATH, ".//span[contains(@class,'selectable-text')]")
        raw = "\n".join([s.text for s in spans if s.text]).strip()
        texto = _normalize(raw)
        return _collapse_tail_repeat(texto)
    except Exception as e:
        print(f"Erro ao obter a última mensagem: {e}")
        return ""

def encontrar_caixa_mensagem(driver):
    candidatos = [
        "//div[@title='Digite uma mensagem']",
        "//div[@contenteditable='true' and @data-tab='10']",
        "//footer//div[@contenteditable='true']",
    ]
    for xp in candidatos:
        try:
            el = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((By.XPATH, xp)))
            return el
        except TimeoutException:
            continue
    return None

def enviar_bloco_multilinha(driver, texto: str):
    """
    Envia um ÚNICO balão multi-linha:
    - Digita cada linha
    - Entre linhas: SHIFT+ENTER (quebra de linha sem enviar)
    - No final: ENTER (envia)
    """
    caixa = encontrar_caixa_mensagem(driver)
    if not caixa:
        raise RuntimeError("Caixa de mensagem não encontrada.")
    caixa.click()
    time.sleep(random.uniform(0.3, 0.7))

    lines = texto.split("\n")
    for i, ln in enumerate(lines):
        if ln:
            caixa.send_keys(ln)
        # aplica quebra de linha (sem enviar) se não for a última
        if i < len(lines) - 1:
            ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
            time.sleep(random.uniform(0.15, 0.35))

    time.sleep(random.uniform(0.5, 1.0))
    caixa.send_keys(Keys.ENTER)

# =========================
# LOOP
# =========================
def main():
    driver = inicializar_driver_stealth()
    if not driver:
        print("Não foi possível iniciar o driver. Encerrando.")
        return

    try:
        abrir_whatsapp_web(driver)

        tarefa_do_dia_concluida = False
        payload_pronto = ""
        ultimo_dia = datetime.now(TZ).date()

        print("Bot ativo. Aguardando janelas (America/Campo_Grande).")

        while True:
            now_tz = datetime.now(TZ)
            hoje = now_tz.date()

            # Reset diário
            if hoje != ultimo_dia:
                ultimo_dia = hoje
                tarefa_do_dia_concluida = False
                payload_pronto = ""
                print(f"({now_tz.strftime('%H:%M:%S')}) Novo dia → reset.")

            if now_tz.hour >= HORA_FIM_VIGILANCIA or now_tz.hour < HORA_INICIO_PREPARACAO:
                time.sleep(30)
                continue

            # PREPARAÇÃO
            if (HORA_INICIO_PREPARACAO <= now_tz.hour < HORA_FIM_VIGILANCIA) and not payload_pronto:
                print(f"({now_tz.strftime('%H:%M:%S')}) Preparando payload. Abrindo grupo…")
                if not abrir_grupo(driver, NOME_DO_GRUPO):
                    time.sleep(random.uniform(2.0, 3.2))
                    continue

                time.sleep(random.uniform(0.8, 1.4))
                texto_lista = obter_texto_ultima_mensagem_preciso(driver)
                if not texto_lista:
                    print(f"({now_tz.strftime('%H:%M:%S')}) Última mensagem vazia. Fallback.")
                    payload_pronto = MENSAGEM_FALLBACK
                else:
                    print("---- LISTA ENCONTRADA (BRUTA) ----")
                    print(texto_lista)
                    print("-----------------------------------")
                    try:
                        struct = parse_sections_flex(texto_lista)
                        ok = add_name_continue_count(struct, SECAO_DA_LISTA, NOME_PARA_ADICIONAR)
                        if not ok:
                            raise RuntimeError(f"Seção '{SECAO_DA_LISTA}' não encontrada.")
                        payload_pronto = rebuild_with_numbering(struct)
                        print("---- LISTA ATUALIZADA (PREVIEW) ----")
                        print(payload_pronto)
                        print("------------------------------------")
                    except Exception as e:
                        print(f"({now_tz.strftime('%H:%M:%S')}) Erro no parsing/edição: {e}. Fallback.")
                        payload_pronto = MENSAGEM_FALLBACK

            # EXECUÇÃO
            if (HORA_INICIO_VIGILANCIA <= now_tz.hour < HORA_FIM_VIGILANCIA) and payload_pronto and not tarefa_do_dia_concluida:
                print(f"({now_tz.strftime('%H:%M:%S')}) Envio. Abrindo grupo…")
                if not abrir_grupo(driver, NOME_DO_GRUPO):
                    time.sleep(random.uniform(2.5, 4.0))
                    continue

                time.sleep(random.uniform(1.2, 2.2))
                if SEND_MESSAGES:
                    try:
                        enviar_bloco_multilinha(driver, payload_pronto)
                        print(f"({now_tz.strftime('%H:%M:%S')}) Enviado com sucesso.")
                    except WebDriverException as e:
                        print(f"({now_tz.strftime('%H:%M:%S')}) Falha ao enviar: {e}. Nova tentativa depois.")
                        time.sleep(random.uniform(2.0, 3.0))
                        continue
                else:
                    print("ENVIO DESATIVADO (SEND_MESSAGES=False). Mensagem que seria enviada:")
                    print("====================================")
                    print(payload_pronto)
                    print("====================================")

                tarefa_do_dia_concluida = True
                print(f"({now_tz.strftime('%H:%M:%S')}) Tarefa concluída.")

            time.sleep(random.uniform(0.8, 1.6))

    except KeyboardInterrupt:
        print("Encerrado por KeyboardInterrupt.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
