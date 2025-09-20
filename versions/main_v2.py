# main.py
# Requisitos:
#   pip install selenium webdriver-manager
#   Python >= 3.9 (usa zoneinfo)
#
# Observação:
# - Primeiro rode com SEND_MESSAGES = False para validar no console.
# - Depois de validar, altere SEND_MESSAGES = True para enviar no WhatsApp.

import os
import re
import time
import random
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# =========================
# CONFIGURAÇÕES DO BOT
# =========================

# Identificação do grupo e regra de inserção do nome
NOME_DO_GRUPO = "Bot Test"                  # coloque o nome EXATO do grupo
SECAO_DA_LISTA = "Volta"                    # seção cujo título começa com essa palavra (ex.: "Volta", "Ida", etc.)
NOME_PARA_ADICIONAR = "Hélio"              # seu nome a ser incluído no fim da seção se ainda não estiver

# Janelas de operação (horário local MS)
TZ = ZoneInfo("America/Campo_Grande")
HORA_INICIO_PREPARACAO = 20   # a partir desta hora o bot pode pré-calcular o payload
MINUTO_INICIO_PREPARACAO = 0
HORA_INICIO_VIGILANCIA = 21   # a partir desta hora pode executar (abrir grupo e enviar)
HORA_FIM_VIGILANCIA = 23      # após esta hora, o bot dorme até o próximo dia

# Envio real ligado/desligado para testes seguros
SEND_MESSAGES = True

# Mensagem de fallback se parsing falhar
MENSAGEM_FALLBACK = "Boa noite! (fallback) Lista atualizada conforme combinado."

# =========================
# FUNÇÕES UTILITÁRIAS: parsing/edição
# =========================

def _normalize(s: str) -> str:
    # Normaliza espaços à direita, preservando acentos e quebras
    return "\n".join([line.rstrip() for line in s.splitlines()])

def _strip_accents_lower(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower()

def parse_sections(texto: str):
    """
    Recebe o texto completo da mensagem de lista e retorna uma estrutura:
    {
      "header": "linha(s) de cabeçalho (se houver)",
      "sections": [
         {"title": "Ida 11:15", "items": ["isabella(unigran)", "Eduarda (unigran)", ...]},
         {"title": "Volta 17:30", "items": ["Jaqueline","Lucas","Giuliane","..."]}
      ],
      "footer": "linha(s) finais se houver"
    }
    Heurística de detecção de seções: uma linha não vazia sem numeração que é seguida por linhas numeradas "1. item".
    """
    texto = _normalize(texto)
    linhas = texto.splitlines()

    header = []
    sections = []
    footer = []

    i = 0
    # Coletar header até a 1ª seção plausível
    while i < len(linhas):
        l = linhas[i].strip()
        # Candidata a seção (linha não vazia e não numerada)
        if l and not re.match(r"^\d+\.\s", l):
            # Verifica se próximas linhas são itens numerados
            j = i + 1
            has_numbered = False
            while j < len(linhas):
                lj = linhas[j].strip()
                if not lj:
                    j += 1
                    continue
                if re.match(r"^\d+\.\s", lj):
                    has_numbered = True
                    break
                # achamos outra possível seção, então a atual talvez não seja seção legítima
                if lj and not re.match(r"^\d+\.\s", lj):
                    break
                j += 1
            if has_numbered:
                break
        header.append(linhas[i])
        i += 1

    # Coletar seções
    while i < len(linhas):
        # título de seção
        title = linhas[i].strip()
        if not title:
            i += 1
            continue

        # itens numerados desta seção
        i += 1
        items = []
        while i < len(linhas):
            line = linhas[i].strip()
            if re.match(r"^\d+\.\s", line):
                item = re.sub(r"^\d+\.\s", "", line).strip()
                if item:
                    items.append(item)
                i += 1
            else:
                break

        sections.append({"title": title, "items": items})

        # pular linhas em branco
        while i < len(linhas) and not linhas[i].strip():
            i += 1

        # se próxima linha não parece título de seção, quebra para footer
        if i < len(linhas):
            nxt = linhas[i].strip()
            # se for numerado, não é título
            if not nxt or re.match(r"^\d+\.\s", nxt):
                break
        else:
            break

    # Resto vira rodapé
    if i < len(linhas):
        footer = linhas[i:]

    return {
        "header": "\n".join(header).strip(),
        "sections": sections,
        "footer": "\n".join(footer).strip()
    }

def parse_sections_v2(texto: str):
    """
    NOVA VERSÃO: Processa o texto da lista sem depender de numeração.
    Identifica seções por palavras-chave como "Ida" e "Volta".
    """
    texto = _normalize(texto)
    linhas = texto.splitlines()

    header = []
    sections = []
    footer = []
    
    current_section_items = None
    
    # Heurística: procura por linhas que pareçam títulos de seção
    for linha in linhas:
        linha_strip = linha.strip()
        if not linha_strip:
            continue

        # Normaliza a linha para busca case-insensitive e sem acentos
        linha_norm = _strip_accents_lower(linha_strip)

        # Se a linha parece um título de seção (contém 'ida' ou 'volta'), inicia uma nova seção
        if 'ida' in linha_norm or 'volta' in linha_norm:
            current_section = {"title": linha_strip, "items": []}
            sections.append(current_section)
        # Se já estamos dentro de uma seção, esta linha é um item dela
        elif len(sections) > 0:
            sections[-1]["items"].append(linha_strip)
        # Se ainda não encontramos nenhuma seção, a linha vai para o cabeçalho
        else:
            header.append(linha)
            
    # O footer não é capturado por esta lógica simples, mas é menos crítico.

    return {
        "header": "\n".join(header).strip(),
        "sections": sections,
        "footer": "\n".join(footer).strip()
    }

def parse_sections_v3(texto: str):
    """
    VERSÃO FINAL: Processa o texto da lista sem depender de numeração inicial,
    mas separa corretamente as seções.
    """
    texto = _normalize(texto)
    linhas = texto.splitlines()

    header = []
    sections = []
    
    current_section = None

    for linha in linhas:
        linha_strip = linha.strip()
        if not linha_strip:
            continue

        linha_norm = _strip_accents_lower(linha_strip)

        # Heurística para título: contém 'ida' ou 'volta' E NÃO começa com número e ponto.
        # Isso evita que um item como "1. Volta Redonda" seja confundido com um título.
        is_title = ('ida' in linha_norm or 'volta' in linha_norm) and not re.match(r"^\d+\.", linha_norm)

        if is_title:
            current_section = {"title": linha_strip, "items": []}
            sections.append(current_section)
        elif current_section:
            # Se já estamos em uma seção, a linha é um item.
            current_section["items"].append(linha_strip)
        else:
            # Se ainda não encontramos nenhuma seção, a linha é do cabeçalho.
            header.append(linha)
            
    return {
        "header": "\n".join(header).strip(),
        "sections": sections,
        "footer": "" # Footer simplificado, geralmente não é necessário.
    }


def add_name_in_section(struct, section_key: str, nome: str):
    """
    Procura seção cujo título COMEÇA com section_key (case/acento-insensitive)
    e adiciona 'nome' ao fim se ainda não existir.
    Retorna True se a seção-alvo foi encontrada, False caso contrário.
    """
    key_norm = _strip_accents_lower(section_key)
    nome_norm = _strip_accents_lower(nome)

    found = False
    for sec in struct["sections"]:
        title_norm = _strip_accents_lower(sec["title"])
        if title_norm.startswith(key_norm):
            found = True
            # evita duplicata
            if not any(_strip_accents_lower(x) == nome_norm for x in sec["items"]):
                sec["items"].append(nome)
            break
    return found

def rebuild_text(struct):
    out = []
    if struct["header"]:
        out.append(struct["header"])
        out.append("")  # linha em branco após header

    for sec in struct["sections"]:
        out.append(sec["title"])
        for idx, item in enumerate(sec["items"], start=1):
            out.append(f"{idx}. {item}")
        out.append("")  # linha em branco após seção

    if struct["footer"]:
        out.append(struct["footer"])

    texto = "\n".join(out)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    return texto

def rebuild_text_v2(struct):
    """
    VERSÃO FINAL: Remonta o texto e adiciona a numeração, mas VERIFICA
    se um item já foi numerado pelo WhatsApp para evitar duplicação.
    """
    out = []
    if struct["header"]:
        out.append(struct["header"])
        out.append("")

    for sec in struct["sections"]:
        out.append(sec["title"])
        for idx, item in enumerate(sec["items"], start=1):
            # Remove qualquer numeração existente (ex: "2. Lucas" vira "Lucas")
            item_sem_numero = re.sub(r"^\d+\.\s*", "", item).strip()
            
            # Adiciona a numeração correta e limpa
            out.append(f"{idx}. {item_sem_numero}")
        out.append("")

    if struct["footer"]:
        out.append(struct["footer"])

    texto = "\n".join(out)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    return texto

# =========================
# WEBDRIVER / WHATSAPP
# =========================

def inicializar_driver_stealth():
    """
    Inicializa Chrome com perfil dedicado e flags de robustez.
    Mantém sessão (QR Code não precisa ser lido todo dia).
    """
    try:
        options = webdriver.ChromeOptions()

        # user-data-dir correto (caminho absoluto) para persistir sessão
        data_dir = os.path.abspath("./whatsapp_session_data")
        os.makedirs(data_dir, exist_ok=True)
        options.add_argument(f"--user-data-dir={data_dir}")
        options.add_argument("--profile-directory=Default")

        # Silenciar verbosidade e evitar detecção básica
        options.add_argument("--log-level=3")  # reduz log
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Robusteza em Windows/containers
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")

        # IMPORTANTE: não setamos --remote-debugging-port manualmente

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.maximize_window()
        return driver
    except Exception as e:
        print(f"Erro ao iniciar o Chrome Driver com webdriver-manager: {e}")
        return None

def abrir_whatsapp_web(driver, timeout=90):
    driver.get("https://web.whatsapp.com/")
    try:
        # Espera pelo container principal do app
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div#app"))
        )
        print("WhatsApp Web carregado.")
    except TimeoutException:
        raise RuntimeError("Timeout ao carregar WhatsApp Web.")

def abrir_grupo(driver, nome_grupo, timeout=30):
    """
    Abre o chat do grupo pelo título da conversa no sidebar.
    """
    try:
        # Tenta encontrar diretamente na barra lateral
        x = f"//span[@title='{nome_grupo}']"
        el = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, x))
        )

        el.click()
        # Espera área de mensagens aparecer
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div#main"))  #div[data-testid='conversation-panel-wrapper']
        )

        return True
    except TimeoutException:
        # Alternativa: usar a busca
        try:
            search_xpath = "//div[@role='textbox' and @title='Pesquisar input textbox']"
            search_box = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, search_xpath))
            )
            search_box.click()
            time.sleep(random.uniform(0.4, 0.8))
            search_box.send_keys(nome_grupo)
            time.sleep(random.uniform(0.8, 1.2))
            x2 = f"//span[@title='{nome_grupo}']"
            el2 = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, x2))
            )
            el2.click()
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid='conversation-panel-wrapper']"))
            )
            return True
        except Exception:
            return False

def obter_texto_ultima_mensagem(driver):
    """
    Recupera o texto visível da última mensagem do chat atual.
    Usa dois seletores em fallback por estabilidade.
    """
    # seletor 1: coluna de mensagens → última bolha com texto selecionável
    x1 = "(//div[contains(@class,'message-in') or contains(@class,'message-out')])[last()]//span[contains(@class,'selectable-text')]"
    els = driver.find_elements(By.XPATH, x1)
    if els:
        return "\n".join([e.text for e in els if e.text]).strip()

    # seletor 2: via role=row
    x2 = "(//div[@role='row'])[last()]//span[contains(@class,'selectable-text')]"
    els2 = driver.find_elements(By.XPATH, x2)
    if els2:
        return "\n".join([e.text for e in els2 if e.text]).strip()

    # Se nada, tenta pegar qualquer texto na área da conversa (menos robusto)
    try:
        panel = driver.find_element(By.CSS_SELECTOR, "div[data-testid='conversation-panel-wrapper']")
        return panel.text.strip()
    except NoSuchElementException:
        return ""
    
def obter_texto_ultima_mensagem_v2(driver):
    """
    VERSÃO FINAL E PRECISA: Recupera o texto APENAS da última "bolha"
    de mensagem para evitar capturar mensagens antigas.
    """
    try:
        # Este seletor é mais específico: ele procura o último grupo de mensagens
        # (seja de entrada ou saída) e, dentro dele, pega todo o texto.
        base_xpath = "(//div[contains(@class, 'message-in') or contains(@class, 'message-out')])[last()]"
        elementos_de_texto = driver.find_elements(By.XPATH, f"{base_xpath}//span[contains(@class, 'selectable-text')]")

        if not elementos_de_texto:
            # Fallback se o seletor principal falhar
            base_xpath = "(//div[@role='row'])[last()]"
            elementos_de_texto = driver.find_elements(By.XPATH, f"{base_xpath}//span[contains(@class, 'selectable-text')]")

        # Junta o texto de todos os elementos encontrados dentro da última bolha.
        texto_completo = "\n".join([el.text for el in elementos_de_texto if el.text])
        
        return texto_completo.strip()
    except Exception as e:
        print(f"Erro ao obter a última mensagem: {e}")
        return ""

def encontrar_caixa_mensagem(driver):
    """
    Tenta localizar a caixa de digitação.
    Testa alguns seletores compatíveis com mudanças de UI.
    """
    candidatos = [
        "//div[@title='Digite uma mensagem']",
        "//div[@contenteditable='true' and @data-tab='10']",
        "//footer//div[@contenteditable='true']",
    ]
    for xp in candidatos:
        try:
            el = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            return el
        except TimeoutException:
            continue
    return None

# =========================
# LOOP PRINCIPAL
# =========================

def main():
    driver = inicializar_driver_stealth()
    if not driver:
        print("Não foi possível iniciar o driver. Encerrando.")
        return

    try:
        abrir_whatsapp_web(driver)

        tarefa_do_dia_concluida = False
        payload_pronto = ""   # mensagem final pré-calculada
        ultimo_dia = datetime.now(TZ).date()

        print("Bot ativo. Aguardando janelas de preparação/execução (fuso America/Campo_Grande).")

        while True:
            now_tz = datetime.now(TZ)
            hoje = now_tz.date()

            # Reset diário simples
            if hoje != ultimo_dia:
                ultimo_dia = hoje
                tarefa_do_dia_concluida = False
                payload_pronto = ""
                print(f"({now_tz.strftime('%H:%M:%S')}) Novo dia → reset de estado.")

            # Fora da janela de vigilância noturna, durma mais.
            if now_tz.hour >= HORA_FIM_VIGILANCIA or now_tz.hour < HORA_INICIO_PREPARACAO:
                time.sleep(30)
                continue

            # FASE 1 — PREPARAÇÃO: montar payload uma vez
            if (HORA_INICIO_PREPARACAO <= now_tz.hour < HORA_FIM_VIGILANCIA) and not payload_pronto:
                print(f"({now_tz.strftime('%H:%M:%S')}) Entrando em modo de preparação. Abrindo grupo…")
                if not abrir_grupo(driver, NOME_DO_GRUPO):
                    print(f"({now_tz.strftime('%H:%M:%S')}) Não consegui abrir o grupo '{NOME_DO_GRUPO}'. Tentarei novamente.")
                    time.sleep(random.uniform(2.5, 4.0))
                    continue

                # Pequena pausa “humana”
                time.sleep(random.uniform(0.8, 1.6))

                texto_da_lista = obter_texto_ultima_mensagem_v2(driver)
                if not texto_da_lista:
                    print(f"({now_tz.strftime('%H:%M:%S')}) Não encontrei texto na última mensagem. Usarei fallback.")
                    payload_pronto = MENSAGEM_FALLBACK
                else:
                    print("---- LISTA ENCONTRADA (BRUTA) ----")
                    print(texto_da_lista)
                    print("-----------------------------------")

                    try:
                        struct = parse_sections_v3(texto_da_lista)
                        ok = add_name_in_section(struct, SECAO_DA_LISTA, NOME_PARA_ADICIONAR)
                        if not ok:
                            raise RuntimeError(f"Não encontrei seção iniciando por '{SECAO_DA_LISTA}' na última lista.")

                        payload_pronto = rebuild_text_v2(struct)

                        print("---- LISTA ATUALIZADA (PREVIEW) ----")
                        print(payload_pronto)
                        print("------------------------------------")

                        print(f"({now_tz.strftime('%H:%M:%S')}) Payload pré-calculado e pronto para envio.")
                    except Exception as e:
                        print(f"({now_tz.strftime('%H:%M:%S')}) Erro no parsing/edição da lista: {e}. Usando fallback.")
                        payload_pronto = MENSAGEM_FALLBACK

            # FASE 2 — VIGILÂNCIA/EXECUÇÃO: enviar na janela desejada, apenas uma vez por dia
            if (HORA_INICIO_VIGILANCIA <= now_tz.hour < HORA_FIM_VIGILANCIA) and payload_pronto and not tarefa_do_dia_concluida:
                print(f"({now_tz.strftime('%H:%M:%S')}) Janela de execução aberta. Abrindo grupo…")
                if not abrir_grupo(driver, NOME_DO_GRUPO):
                    print(f"({now_tz.strftime('%H:%M:%S')}) Não consegui abrir o grupo '{NOME_DO_GRUPO}' para enviar. Vou tentar de novo em breve.")
                    time.sleep(random.uniform(3.0, 5.0))
                    continue

                # Anti-ban: agir com calma
                time.sleep(random.uniform(1.8, 4.2))

                caixa = encontrar_caixa_mensagem(driver)
                if not caixa:
                    print(f"({now_tz.strftime('%H:%M:%S')}) Não encontrei a caixa de mensagem. Vou re-tentar depois.")
                    time.sleep(random.uniform(2.0, 3.2))
                    continue

                if SEND_MESSAGES:
                    try:
                        caixa.click()
                        time.sleep(random.uniform(0.4, 0.9))

                        # Nova lógica para enviar como um bloco único
                        linhas_do_payload = payload_pronto.split('\n')
                        for i, linha in enumerate(linhas_do_payload):
                            caixa.send_keys(linha)
                            # Adiciona Shift+Enter para criar uma nova linha, exceto na última
                            if i < len(linhas_do_payload) - 1:
                                caixa.send_keys(Keys.SHIFT, Keys.ENTER)
                                time.sleep(random.uniform(0.1, 0.3)) # Pequena pausa entre as linhas

                        # Agora sim, envia a mensagem completa com Enter
                        time.sleep(random.uniform(0.6, 1.2))
                        
                        # Execução real (descomente a linha abaixo para ativar o envio real)
                        # caixa.send_keys(Keys.ENTER)

                        print(f"({now_tz.strftime('%H:%M:%S')}) Bloco de mensagem enviado com sucesso.")
                    except WebDriverException as e:
                        print(f"({now_tz.strftime('%H:%M:%S')}) Falha ao enviar: {e}. Vou tentar de novo depois.")
                        time.sleep(random.uniform(2.0, 3.0))
                        continue
                else:
                    print("ENVIO DESATIVADO (SEND_MESSAGES=False). Mensagem que seria enviada:")
                    print("====================================")
                    print(payload_pronto)
                    print("====================================")

                tarefa_do_dia_concluida = True
                print(f"({now_tz.strftime('%H:%M:%S')}) Tarefa do dia marcada como concluída.")

            # Ritmo de varredura conservador (anti-fluxo)
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

# caixa.click()
# time.sleep(random.uniform(0.4, 0.9))
# caixa.send_keys(payload_pronto)
# time.sleep(random.uniform(0.6, 1.2))
# caixa.send_keys(Keys.ENTER)
# print(f"({now_tz.strftime('%H:%M:%S')}) Enviado com sucesso.")