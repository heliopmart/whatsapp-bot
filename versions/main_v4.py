import os, re, time, random, unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
import pyperclip
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def get_mock_whatsapp_output():
    """
    Retorna uma string de teste multilinha que simula a saída duplicada 
    do scraper do WhatsApp, preservando a formatação e caracteres especiais.
    """
    # Esta string é uma cópia fiel da sua saída "raw" para testes.
    return """  Quinta-feira 18/09 
Ida 11:15
Jaqueline
⁠Thalya ( Anhanguera)
Kleber
Maria Fernanda (unigran)
Débora (unigran)
Isabelly (Unigran)
Volta 17:30
Jaqueline
⁠Antonio
⁠Aline (unigran)
Lucas
⁠Tainá (Unigran)
João
Giovana
Kleber
Raffaela
⁠Isadora (unigran)
⁠Beatriz"""

class WhatsAppBot:
    def __init__(self, groupName='Bot Test', whatList=1):
        self.driver = None
        self.sendMensage = False

        self.timeZone = ZoneInfo("America/Campo_Grande")
        self.hourStartBot = 20
        self.hourFinishBot = 23

        self.ZWSP = "\u200b"

        self.groupName = groupName # Lembre de usar seu grupo de teste
        self.nameToAdd = 'Helio'
        # 0 -> Apenas Volta e 1 -> Ida e Volta
        self.whatList = whatList

        self.list_sent_for_today = False
        self.last_check_date = None

    def main(self):
        self.open_whatsapp_web()
        group_list = self.get_list_from_whatsapp()
        # temp_group_list = self.temp_get_list_from_whatsapp()
        back_list, go_list = self.parse_schedule_robust(group_list)
        back_list_with_name, go_list_with_name = self.put_name_in_list(go_list, back_list)
        reconstruct_list = self.reconstruct_list(back_list_with_name, go_list_with_name)
        
        self.send_message_via_clipboard(self.driver, reconstruct_list)

        print(f"Lista extraída: \n {group_list} \n\n")
        # print(f"Lista extraída: \n {temp_group_list} \n\n")
        print(f"Lista extraída normalizada: \n {self.parse_schedule_robust(group_list)}")
        print(f'Go List with name: \n {go_list_with_name} \n')
        print(f'Back List with name: \n {back_list_with_name} \n')
        print(f"Reconstructed List: \n {reconstruct_list} \n")

        input("Pressione Enter para sair...")

    def is_group_open(self):
        """
        Verifica se o grupo está aberto para não-admins, procurando pela caixa de texto.
        Retorna True se estiver aberto, False caso contrário.
        """
        try:
            # Usamos um tempo de espera bem curto (1-2 segundos)
            # Se a caixa de texto for encontrada rápido, o grupo está aberto.
            xp_input_box = "//div[@role='textbox' and @data-testid='conversation-compose-box-input']"
            WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.XPATH, xp_input_box))
            )
            return True
        except TimeoutException:
            # Se estourar o tempo, a caixa não existe, então o grupo está fechado.
            return False

    def search_input_text(self):
        candidatos = [
            "//div[@title='Digite uma mensagem']",
            "//div[@contenteditable='true' and @data-tab='10']",
            "//footer//div[@contenteditable='true']",
        ]
        for xp in candidatos:
            try:
                el = WebDriverWait(self.driver, 6).until(EC.element_to_be_clickable((By.XPATH, xp)))
                return el
            except TimeoutException:
                continue
        return None

    def send_message_via_clipboard(self, driver, message):
        """
        Copia a mensagem para o clipboard e a cola no chat do WhatsApp.
        """
        # 1. Copia a mensagem formatada para a área de transferência
        pyperclip.copy(message)
        
        # 2. Encontra o campo de digitação do WhatsApp
        # (O seletor pode variar, este é um exemplo comum)
        chatbox = self.search_input_text()
        chatbox.click()

        # 3. Simula o "Ctrl+V" (ou Command+V no Mac)
        # Use Keys.COMMAND no lugar de Keys.CONTROL se estiver no macOS
        chatbox.send_keys(Keys.CONTROL, 'v')
        
        if(self.sendMensage == True):
            chatbox.send_keys(Keys.ENTER)
            print("Mensagem enviada com sucesso!")
        else:
            print("Em Aguardo!")
        
    def reconstruct_list(self, back_list, go_list):
        fullList = ''
        for i, name in enumerate(go_list):
            if(name == '11:15'):
                fullList += f"Ida {name} \n"
            else:
                fullList += f" {i+1}.{self.ZWSP}{name.title()} \n"

        for i, name in enumerate(back_list):
            if(name == '17:30'):
                fullList += f" \n Volta {name} \n"
            else:
                fullList += f" {i+1}.{self.ZWSP}{name.title()} \n"

        return fullList

    def put_name_in_list(self, go_list, back_list):
        if(self.whatList == 0):
            back_list.append(self.nameToAdd.lower())
        else:
            go_list.append(self.nameToAdd.lower())
            back_list.append(self.nameToAdd.lower())
        
        return go_list, back_list

    def open_whatsapp_web(self):
        whatsapp = Whatsapp(self.groupName)
        self.driver = whatsapp.main()

    def temp_get_list_from_whatsapp(self):
        return get_mock_whatsapp_output()

    def get_list_from_whatsapp(self):
        """
            Extrai o texto da ÚLTIMA bolha de mensagem de forma estruturada,
            mirando no contêiner de conteúdo principal.
        """
        try:
            # 1. Encontra a "bolha" da última mensagem. Esta parte continua igual.
            last_bubble = self.driver.find_element(
                By.XPATH, 
                "(//div[contains(@class,'message-in') or contains(@class,'message-out')])[last()]"
            )
            
            # 2. Encontra o contêiner de conteúdo DENTRO da bolha.
            # O seletor abaixo procura pelo primeiro <span> que tem a classe '_ao3e' e 'selectable-text'.
            # Este parece ser o contêiner principal do seu HTML.
            content_container = last_bubble.find_element(
                By.XPATH, 
                ".//span[contains(@class, '_ao3e') and contains(@class, 'selectable-text')]"
            )
            
            # 3. Extrai o texto completo e estruturado do contêiner.
            # A propriedade .text é poderosa e vai montar o texto para nós.
            raw_text = content_container.text
            
            print(f"Texto Bruto Extraído:\n---\n{raw_text}\n---")
            
            return raw_text

        except NoSuchElementException:
            print("Não foi possível encontrar a última mensagem ou o contêiner de conteúdo.")
            return ""
        except Exception as e:
            print(f"Ocorreu um erro inesperado: {e}")
            return ""

    def parse_schedule_robust(self, raw_text):
        """
        Recebe o texto bruto e extrai as listas de Ida e Volta de forma robusta.
        Retorna um dicionário com as duas listas limpas.
        """
        
        # Usar split é mais seguro para separar as seções
        try:
            # Separa o bloco de Ida do resto
            before_volta, after_volta = raw_text.split("Volta", 1)
            # Pega só o que vem depois de "Ida"
            ida_block = before_volta.split("Ida", 1)[1]
            volta_block = after_volta
        except ValueError:
            # Retorno seguro caso o texto não tenha os marcadores esperados
            return {'ida': [], 'volta': []}

        # Limpa cada bloco de texto de forma independente
        ida_list = self.clean_name_list(ida_block)
        volta_list = self.clean_name_list(volta_block)
    
        return ida_list, volta_list

    def clean_name_list(self, block_text):
        """Função interna para limpar um bloco de texto e retornar uma lista de nomes."""
        cleaned_list = []
        # Usamos um set para garantir que não haja duplicatas DENTRO da mesma lista
        seen_names = set()
        
        for line in block_text.split('\n'):
            # Limpa o nome: remove números, pontos, caracteres ZWSP e espaços
            name = re.sub(r"^\s*\d+\.\s*", "", line).strip().lower()
            name = name.replace(self.ZWSP, '').strip()

            if name and name not in seen_names:
                cleaned_list.append(name)
                seen_names.add(name)
        return cleaned_list
    
class Whatsapp:
    def __init__ (self, groupName):
        self.groupName = groupName
        self.driver = None
        
    def main(self):
        self.inicializar_driver_stealth()
        self.abrir_whatsapp_web()
        if self.abrir_grupo():
            print(f"Grupo '{self.groupName}' aberto com sucesso.")
            return self.driver
        else:
            print(f"Falha ao abrir o grupo '{self.groupName}'.")

    def inicializar_driver_stealth(self):
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

            self.driver = driver
            return driver
        except Exception as e:
            print(f"Erro ao iniciar o Chrome Driver com webdriver-manager: {e}")
            return None

    def abrir_whatsapp_web(self, timeout=90):
        self.driver.get("https://web.whatsapp.com/")
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div#app"))
        )
        print("WhatsApp Web carregado.")

    def abrir_grupo(self, timeout=25):
        try:
            xp = f"//span[@dir='auto' and @title='{self.groupName}']"
            el = WebDriverWait(self.driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
            
            print(el)
            
            el.click()
            WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div#main")))
            
            print("Grupo aberto.")
            
            return True
        except TimeoutException:
            print(f"Não achei '{self.groupName}' na lateral. Confirme o nome exato (título do span).")
            return False
        

if __name__ == "__main__":
    WhatsAppBot().main()

