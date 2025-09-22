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
import qrcode # <--- ADICIONE ESTA LINHA

pyperclip.set_clipboard("xclip")

class WhatsAppBot:
    def __init__(self, groupName='Bot Test', whatList=1):
        self.driver = None
        self.sendMensage = False

        self.timeZone = ZoneInfo("America/Campo_Grande")
        self.days_to_run = [6, 1, 3]  # Domingo, Terça, Quinta
        self.hourStartBot = 18
        self.hourFinishBot = 23
        self.alert_start_hour = 18
        self.alert_start_minute = 30
        self.alert_end_hour = 21
        self.alert_end_minute = 0

        self.ZWSP = "\u200b"

        self.groupName = groupName # Lembre de usar seu grupo de teste
        self.nameToAdd = 'Helio'
        # 0 -> Apenas Volta e 1 -> Ida e Volta
        self.whatList = whatList

        self.list_sent_for_today = False
        self.last_check_date = None


    def main(self):
        self.open_whatsapp_web()
        
        print("Bot em modo de vigilância 24/7...")

        while True:
            try:
                current_time = datetime.now(self.timeZone)
                current_date = current_time.date()
                day_of_week = current_time.weekday() # Pega o dia da semana atual

                if self.last_check_date != current_date:
                    self.list_sent_for_today = False
                    self.last_check_date = current_date
                    print(f"[{current_time.strftime('%H:%M:%S')}] Novo dia. Bot pronto para a lista de hoje.")

                is_in_time_window = self.hourStartBot <= current_time.hour < self.hourFinishBot
                is_correct_day = day_of_week in self.days_to_run

                if self.list_sent_for_today or not is_in_time_window or not is_correct_day:
                    if not is_correct_day and is_in_time_window and not self.list_sent_for_today:
                        # Log para sabermos por que ele está dormindo
                        print(f"[{current_time.strftime('%H:%M:%S')}] Hoje não é um dia de lista. Bot em espera.")
                    
                    time.sleep(300) # Dorme por 5 minutos
                    continue

                # --- LÓGICA DO MODO DE ALERTA ---
                is_in_alert_window = (
                    (current_time.hour > self.alert_start_hour or 
                    (current_time.hour == self.alert_start_hour and current_time.minute >= self.alert_start_minute)) 
                    and 
                    (current_time.hour < self.alert_end_hour or 
                    (current_time.hour == self.alert_end_hour and current_time.minute < self.alert_end_minute))
                )

                if self.is_group_open():
                    print(f"[{current_time.strftime('%H:%M:%S')}] GRUPO ABERTO! Iniciando operação em velocidade máxima.")
                    
                    group_list = self.get_list_from_whatsapp()

                    if not group_list:
                        print(f"[{current_time.strftime('%H:%M:%S')}] Nenhuma lista encontrada. Tentando novamente em breve.")
                        time.sleep(15) # Espera um pouco antes de verificar de novo
                        continue # Volta para o início do loop while

                    if self.nameToAdd.lower() in group_list.lower():
                        print(f"[{current_time.strftime('%H:%M:%S')}] Meu nome já está na lista. Ação cancelada para hoje.")
                        self.list_sent_for_today = True
                        continue

                    ida_list, volta_list = self.parse_schedule_robust(group_list)
                    go_list_with_name, back_list_with_name = self.put_name_in_list(ida_list, volta_list)
                    reconstruct_list = self.reconstruct_list(back_list_with_name, go_list_with_name)
                    
                    # Ação imediata, sem pausa
                    self.send_message_via_clipboard(reconstruct_list)
                    self.list_sent_for_today = True
                    print(f"[{current_time.strftime('%H:%M:%S')}] Operação concluída. Entrando em modo de espera até amanhã.")

                else:
                    # Decide a duração da pausa com base no modo de alerta
                    if is_in_alert_window:
                        print(f"[{current_time.strftime('%H:%M:%S')}] MODO DE ALERTA. Grupo fechado. Verificando em alta frequência...")
                        sleep_duration = random.uniform(0.7, 1.5)
                    else:
                        print(f"[{current_time.strftime('%H:%M:%S')}] Monitoramento normal. Grupo fechado. Verificando novamente em breve...")
                        sleep_duration = random.uniform(10, 20)
                    
                    time.sleep(sleep_duration)

            except WebDriverException:
                print("Erro crítico com o WebDriver (ex: navegador fechou). Reiniciando...")
                self.open_whatsapp_web()
            except Exception as e:
                print(f"Ocorreu um erro inesperado no loop principal: {e}")
                time.sleep(60)

    def is_group_open(self):
        """
        Verifica se o grupo está aberto para não-admins, procurando pela caixa de texto.
        Retorna True se estiver aberto, False caso contrário.
        """
        try:
            # Usamos um tempo de espera bem curto (1-2 segundos)
            # Se a caixa de texto for encontrada rápido, o grupo está aberto.
            input = self.search_input_text()
            if(input is not None):
                return True
        except TimeoutException:
            # Se estourar o tempo, a caixa não existe, então o grupo está fechado.
            return False

    def search_input_text(self, timeout=6):
        """
        Busca a caixa de texto usando um único XPath combinado para máxima velocidade.
        """
        # Juntamos todos os candidatos em uma única string com o operador '|'
        combined_xpath = (
            "//div[@title='Digite uma mensagem'] | "
            "//div[@contenteditable='true' and @data-tab='10'] | "
            "//footer//div[@contenteditable='true']"
        )
        
        try:
            # Agora fazemos uma única busca que espera no máximo `timeout` segundos
            el = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, combined_xpath))
            )
            return el
        except TimeoutException:
            # Se nenhum dos candidatos for encontrado, retorna None
            return None

    def send_message_via_clipboard(self, message):
        """
        Copia a mensagem para o clipboard e a cola no chat do WhatsApp.
        """
        # 1. Copia a mensagem formatada para a área de transferência
        pyperclip.copy(message)

        print("[DEBUG] Tentativa de cópia para o clipboard concluída.")
            
        # 2. Pega o conteúdo de volta para verificar se a cópia funcionou
        clipboard_content = pyperclip.paste()
        if message in clipboard_content:
            print("[DEBUG] SUCESSO: O conteúdo do clipboard corresponde à mensagem.")
        else:
            print("[ERRO CRÍTICO] FALHA: O conteúdo do clipboard NÃO corresponde à mensagem!")
            print(f"--- Esperado ---\n{message}\n--- Encontrado ---\n{clipboard_content}\n---")
            return
        
        # 2. Encontra o campo de digitação do WhatsApp
        # (O seletor pode variar, este é um exemplo comum)
        chatbox = self.search_input_text()

        if chatbox is None:
            print("[ERRO] A caixa de texto não foi encontrada. O envio falhou.")
            return
        print(f"[DEBUG] Caixa de texto encontrada: {chatbox}")

        chatbox.click()
        time.sleep(0.2)

        # 3. Simula o "Ctrl+V" (ou Command+V no Mac)
        # Use Keys.COMMAND no lugar de Keys.CONTROL se estiver no macOS
        # chatbox.send_keys(Keys.CONTROL, 'v')
        print("[DEBUG] Colando com ActionChains (Ctrl+V)...")
        actions = ActionChains(self.driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL)
        actions.perform()
        print("[DEBUG] Ação de colar executada.")
        
        if(self.sendMensage):
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
                fullList += f" {i}.{self.ZWSP}{name.title()} \n"

        for i, name in enumerate(back_list):
            if(name == '17:30'):
                fullList += f" \n Volta {name} \n"
            else:
                fullList += f" {i}.{self.ZWSP}{name.title()} \n"

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

    def is_message_a_valid_list(self, message_text):
        """
        Verifica se o texto de uma mensagem parece ser uma lista de horários válida.
        Retorna True se contiver os marcadores principais, False caso contrário.
        """
        text = message_text.lower()
        # A nossa heurística principal: uma lista válida deve ter "ida" e "volta".
        return 'ida' in text and 'volta' in text

    def get_list_from_whatsapp(self):
        """
        Extrai o texto da lista mais recente, procurando nas últimas 5 mensagens
        para ignorar mensagens aleatórias que possam ter sido enviadas depois.
        """
        try:
            # Pega as últimas 5 bolhas de mensagem.
            last_messages = self.driver.find_elements(
                By.XPATH, 
                "(//div[contains(@class,'message-in') or contains(@class,'message-out')])[position() > last() - 5]"
            )
            
            # Itera sobre as mensagens da mais nova para a mais antiga
            for message_bubble in reversed(last_messages):
                try:
                    content_container = message_bubble.find_element(
                        By.XPATH, 
                        ".//span[contains(@class, '_ao3e') and contains(@class, 'selectable-text')]"
                    )
                    raw_text = content_container.text

                    # USA A NOVA FUNÇÃO DE VALIDAÇÃO AQUI!
                    if self.is_message_a_valid_list(raw_text):
                        print(f"Lista válida encontrada:\n---\n{raw_text}\n---")
                        return raw_text # Retorna a primeira lista válida que encontrar
                        
                except NoSuchElementException:
                    # Esta bolha pode não ter texto (ex: uma imagem), ignora e continua
                    continue

            print("Nenhuma lista válida encontrada nas últimas 5 mensagens.")
            return "" # Retorna vazio se não encontrar nenhuma lista

        except Exception as e:
            print(f"Ocorreu um erro inesperado ao procurar a lista: {e}")
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
        print("[DEBUG] Iniciando Drivers")
        self.inicializar_driver_stealth()
        print("[DEBUG] Iniciando o método Whatsapp.main...")
        self.abrir_whatsapp_web()
        if self.abrir_grupo():
            print(f"Grupo '{self.groupName}' aberto com sucesso.")
            return self.driver
        else:
            print(f"Falha ao abrir o grupo '{self.groupName}'.")

    def inicializar_driver_stealth(self):
        try:
            options = webdriver.ChromeOptions()

            # Perfil: do ENV ou padrão persistente
            data_dir = os.path.abspath(os.getenv("CHROME_USER_DATA_DIR", "./whatsapp_session_data"))
            self._prepare_user_data_dir(data_dir)
            options.add_argument(f"--user-data-dir={data_dir}")
            options.add_argument("--profile-directory=Default")

            # --- Flags essenciais p/ Docker/CI ---
            # Headless opcional: troque para "--headless=new" se preferir.
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            # -------------------------------------

            options.add_argument("--log-level=3")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            options.add_argument("--disable-gpu")

            # Evita colisão se houver outro Chrome vivo usando a porta padrão:
            options.add_argument(f"--remote-debugging-port={9222 + random.randint(0,999)}")

            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            try:
                driver.maximize_window()
            except Exception:
                pass

            self.driver = driver
            return driver
        except Exception as e:
            print(f"Erro ao iniciar o Chrome Driver com webdriver-manager: {e}")
            return None

    def abrir_whatsapp_web(self, timeout=90):
        if self.driver is None:
            print("Driver não inicializado. Não é possível abrir o WhatsApp Web.")
            return

        self.driver.get("https://web.whatsapp.com/")
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div#app"))
        )
        print("WhatsApp Web carregado.")

        if not self._logged_in():
            print("[INFO] Aguardando autenticação via QR...")
            ok = self._ensure_login_with_qr_updates(refresh_each=25, max_wait=300)
            if not ok:
                raise RuntimeError("Não foi possível autenticar no WhatsApp a tempo.")

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

    def _prepare_user_data_dir(self, data_dir: str):
        """
        Garante a criação do diretório de perfil e remove locks que causam
        'session not created: user data directory is already in use'.
        """
        os.makedirs(data_dir, exist_ok=True)
        for f in ["SingletonLock", "SingletonCookie", "SingletonSocket", "SingletonSharedMemory"]:
            p = os.path.join(data_dir, f)
            try:
                os.remove(p)
            except FileNotFoundError:
                pass    
    
    def _find_qr_canvas(self, timeout=20):
        """
        Retorna o elemento <canvas> do QR do WhatsApp Web.
        Priorizamos o aria-label que você observou: 'Scan this QR code to link a device!'.
        Mantemos fallbacks para variantes do site.
        """
        CANDIDATES = [
            (By.CSS_SELECTOR, 'canvas[aria-label="Scan this QR code to link a device!"]'),
            (By.XPATH, '//canvas[contains(@aria-label,"Scan this QR code")]'),
            (By.XPATH, '//canvas[contains(@aria-label,"Scan") and contains(@aria-label,"QR")]'),
            (By.CSS_SELECTOR, 'div[data-testid="qrcode"] canvas'),
        ]
        wait = WebDriverWait(self.driver, timeout)
        for by, sel in CANDIDATES:
            try:
                el = wait.until(EC.visibility_of_element_located((by, sel)))
                return el
            except Exception:
                continue
        return None

    # --- 2) Detectar e recarregar QR expirado ---
    def _reload_qr_if_needed(self):
        """
        Se o QR expirou, o WhatsApp mostra um cartão com ícone de reload e texto 'Click to reload QR code'.
        Tentamos clicar para gerar um novo QR.
        """
        try:
            # Botão "reload" comum (ícone circular) na área do QR expirado
            reload_candidates = [
                (By.XPATH, '//*[contains(text(),"Click to reload QR code")]/ancestor-or-self::*[1]'),
                (By.XPATH, '//div[@role="button" and .//span[contains(text(),"reload")]]'),
                (By.CSS_SELECTOR, 'div[aria-label*="reload QR"]'),
            ]
            for by, sel in reload_candidates:
                btns = self.driver.find_elements(by, sel)
                if btns:
                    try:
                        btns[0].click()
                        return True
                    except Exception:
                        pass
        except Exception:
            pass
        return False

    # --- 3) Salvar o QR atual em arquivo ---
    def _save_qr(self, path: str) -> bool:
        """
        Salva o PNG do canvas do QR em 'path'.
        Se estiver expirado, tenta recarregar e capturar de novo.
        """
        # Primeiro tenta pegar o canvas
        qr = self._find_qr_canvas(timeout=8)
        if not qr:
            # Talvez expirado -> tenta reload e busca de novo
            if self._reload_qr_if_needed():
                qr = self._find_qr_canvas(timeout=8)
            if not qr:
                return False

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(qr.screenshot_as_png)
            print(f"[INFO] QR salvo em {path}")
            return True
        except Exception as e:
            print(f"[WARN] Falha ao salvar QR: {e}")
            return False

    # --- 4) Loop de atualização até logar ---
    def _logged_in(self) -> bool:
        # Heurística simples: existe caixa de mensagem quando logado
        try:
            self.driver.find_element(By.CSS_SELECTOR, 'div[role="textbox"]')
            return True
        except Exception:
            return False

    def _ensure_login_with_qr_updates(self, refresh_each=20, max_wait=300) -> bool:
        """
        Atualiza o QR code, priorizando a exibição no terminal para login rápido.
        Salva o arquivo .png como um fallback.
        Para quando detectar login ou quando o tempo máximo for atingido.
        """
        qr_path = os.getenv("QR_OUTPUT_PATH", "/shared/qr.png")
        start_time = time.time()
        last_qr_data = None 

        print("[INFO] Aguardando autenticação via QR Code...")

        while time.time() - start_time < max_wait:
            if self._logged_in():
                print("[INFO] Login bem-sucedido!")
                if os.path.exists(qr_path):
                    try:
                        os.remove(qr_path)
                    except OSError:
                        pass
                return True

            try:
                qr_div = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-ref]"))
                )
                current_qr_data = qr_div.get_attribute("data-ref")

                if current_qr_data and current_qr_data != last_qr_data:
                    print("\n[AÇÃO NECESSÁRIA] Escaneie o QR Code abaixo com seu celular:")
                    
                    # --- INÍCIO DA CORREÇÃO ---
                    # Em vez de qrcode.print_tty(current_qr_data), usamos:
                    qr = qrcode.QRCode()
                    qr.add_data(current_qr_data)
                    qr.print_ascii() # Este é o método correto
                    # --- FIM DA CORREÇÃO ---

                    print("="*60)
                    last_qr_data = current_qr_data
                    
                    self._save_qr(qr_path)

            except (TimeoutException, NoSuchElementException):
                print("[DEBUG] QR Code não encontrado, tentando recarregar e salvar imagem de fallback...")
                if self._save_qr(qr_path):
                    print("[INFO] Imagem de fallback qr.png atualizada.")
                time.sleep(5)
            except Exception as e:
                print(f"[AVISO] Ocorreu um erro ao tentar exibir o QR no terminal: {e}")
                time.sleep(5)

            time.sleep(1)

        print("[ERRO] Tempo máximo de espera para login via QR Code excedido.")
        return False
            

if __name__ == "__main__":
    bot = WhatsAppBot()
    try:
        bot.main()
    except Exception as e:
        print(f"Uma exceção não tratada ocorreu: {e}")
    finally:
        if bot.driver:
            print("Encerrando o driver do Selenium para garantir um desligamento limpo...")
            bot.driver.quit()