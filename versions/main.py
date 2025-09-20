import time
import re
import random
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import os
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURAÇÃO ---
NOME_DO_GRUPO = "Bot Test" # Lembre de usar seu grupo de teste
NOME_PARA_ADICIONAR = "Helio (UFGD)"
SECAO_DA_LISTA = "Volta"
MENSAGEM_FALLBACK = NOME_PARA_ADICIONAR

HORA_INICIO_PREPARACAO = 20
MINUTO_INICIO_PREPARACAO = 00
HORA_INICIO_VIGILANCIA = 20
HORA_FIM_VIGILANCIA = 22

# Adicione estas duas linhas no topo do seu arquivo .py
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

def inicializar_driver_stealth():
    try:
        options = webdriver.ChromeOptions()

        # 1) user-data-dir CORRETO + caminho absoluto e limpo
        data_dir = os.path.abspath("./whatsapp_session_data")
        os.makedirs(data_dir, exist_ok=True)
        options.add_argument(f"--user-data-dir={data_dir}")
        # (opcional) escolha um profile
        options.add_argument("--profile-directory=Default")

        # 2) Evitar prompts iniciais do Chrome
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")

        # 3) Estabilidade em Windows
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")

        # 4) Evitar detecção básica
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--disable-blink-features=AutomationControlled")

        # 5) (Importante!) Deixe o Selenium escolher uma porta de DevTools
        #    Sem definir manualmente --remote-debugging-port.
        #    O user-data-dir já satisfaz a exigência do Chrome.

        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        print(f"Erro ao iniciar o Chrome Driver com webdriver-manager: {e}")
        return None

# --- O CICLO DE OPERAÇÃO CONTÍNUO ---
if __name__ == "__main__":
    # Certifique-se de que todo o código abaixo está corretamente indentado dentro deste bloco
    driver = inicializar_driver_stealth()
    if not driver:
        exit("Não foi possível iniciar o driver. Encerrando.")

    driver.get("https://web.whatsapp.com/")
    print("Por favor, faça o login com QR Code se necessário.")
    print("Aguardando o carregamento completo do WhatsApp Web...")
    
    # Espera inicial robusta para o WhatsApp carregar pela primeira vez
    try:
        WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((By.XPATH, "//canvas[@aria-label='Scan me!'] | //div[@id='pane-side']"))
        )
        print("WhatsApp Web carregado.")
        # Lógica para encontrar e clicar no grupo uma vez
        group_xpath = f"//span[@title='{NOME_DO_GRUPO}']"
        group_element = WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, group_xpath))
        )
        group_element.click()
        print(f"Grupo '{NOME_DO_GRUPO}' selecionado. Iniciando ciclo de operação.")
    except Exception as e:
        exit(f"Não foi possível encontrar o grupo ou carregar o WhatsApp: {e}")

    # Variáveis de estado do ciclo diário
    tarefa_do_dia_concluida = False
    payload_pronto = ""

    while True:
        now = datetime.now()
        
        # --- RESET DIÁRIO ---
        # Se já passou da meia-noite, reseta o estado para o novo dia.
        if now.hour == 0 and tarefa_do_dia_concluida:
            print(f"({now.strftime('%H:%M:%S')}) Novo dia! Resetando o status da tarefa.")
            tarefa_do_dia_concluida = False
            payload_pronto = ""

        if tarefa_do_dia_concluida:
            time.sleep(600) # Se já fez a tarefa, dorme por 10 minutos antes de checar de novo
            continue

        # --- FASE 1: PREPARAÇÃO (Pré-caching do Payload) ---
        if (now.hour == HORA_INICIO_PREPARACAO and now.minute >= MINUTO_INICIO_PREPARACAO) or (now.hour >= HORA_INICIO_VIGILANCIA):
            if not payload_pronto:
                print(f"({now.strftime('%H:%M:%S')}) Entrando em modo de preparação. Procurando a lista...")
                try:
                    last_message_xpath = "(//div[@role='row']) [last()] //span[contains(@class, 'selectable-text')]"
                    last_message_element = driver.find_elements(By.XPATH, last_message_xpath)[-1]
                    texto_da_lista = last_message_element.text
                    
                    # Validação mínima: a lista tem que conter a seção que queremos editar
                    if SECAO_DA_LISTA in texto_da_lista:
                        # (A lógica de edição da lista é a mesma de antes)
                        # ...
                        # Se a lógica for bem-sucedida, ela preenche a variável 'mensagem_a_enviar'
                        # ...
                        payload_pronto = "..." # Substitua '...' pela variável com a mensagem final
                        print(f"({now.strftime('%H:%M:%S')}) ✅ Payload pré-calculado e pronto para envio!")
                    else:
                        print(f"({now.strftime('%H:%M:%S')}) Última mensagem não parece ser a lista. Tentando de novo em 15s.")
                        time.sleep(15)
                except Exception as e:
                    print(f"({now.strftime('%H:%M:%S')}) Erro ao tentar preparar o payload: {e}. Usando fallback.")
                    payload_pronto = MENSAGEM_FALLBACK # Se tudo der errado, prepara o fallback


        # --- FASE 2: VIGILÂNCIA DE ALTA FREQUÊNCIA ---
        if HORA_INICIO_VIGILANCIA <= now.hour < HORA_FIM_VIGILANCIA:
            if payload_pronto:
                try:
                    admin_only_banner_xpath = "//div[@class='_aigv']//span[contains(text(),'Apenas administradores podem')]"
                    driver.find_element(By.XPATH, admin_only_banner_xpath)
                    time.sleep(random.uniform(0.05, 0.1)) # Escuta frenética
                
                except NoSuchElementException:
                    # --- FASE 3: EXECUÇÃO INSTANTÂNEA ---
                    print(f"({now.strftime('%H:%M:%S.%f')}) 🚀 GRUPO ABERTO! ENVIANDO PAYLOAD PRÉ-CALCULADO! 🚀")
                    message_box_xpath = "//div[@title='Digite uma mensagem']"
                    
                    # Execusão do envio (descomente a linha abaixo para ativar o envio real)
                     
                    # message_box = driver.find_element(By.XPATH, message_box_xpath)
                    # message_box.send_keys(payload_pronto + Keys.ENTER)
                    
                    print(f"({now.strftime('%H:%M:%S.%f')}) Missão cumprida!")
                    tarefa_do_dia_concluida = True
            else:
                # Se estiver no horário mas o payload não estiver pronto, avisa e espera.
                print(f"({now.strftime('%H:%M:%S')}) No horário de vigilância, mas o payload ainda não está pronto.")
                time.sleep(10)
        else:
            # Fora de todas as fases, apenas espera.
            print(f"({now.strftime('%H:%M:%S')}) Aguardando horário de preparação ({HORA_INICIO_PREPARACAO}:{MINUTO_INICIO_PREPARACAO})...")
            time.sleep(300)