import requests
import json
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from datetime import datetime
import sys
import threading
import queue
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

class HiggsfieldMultiAccountMonitor:
    def __init__(self, profile_id=0):
        self.api_base = "http://65.109.68.29:9090"
        self.accounts_file = "/home/kul1ght/Desktop/Higgsfield/accounts.txt"
        self.results_file = f"/home/kul1ght/Desktop/Higgsfield/multi_account_results_profile_{profile_id}.json"
        self.used_accounts_file = "/home/kul1ght/Desktop/Higgsfield/used_accounts.txt"
        self.profile_id = profile_id
        self.lock = threading.Lock()
        self.setup_logging()
        self.processed_accounts = self.load_processed_accounts()
        self.driver = None
        self.account_queue = queue.Queue()

    def setup_logging(self):

        log_file = f'/home/kul1ght/Desktop/Higgsfield/multi_account_profile_{self.profile_id}.log'

        logger = logging.getLogger(f'HiggsfieldMonitor_{self.profile_id}')
        logger.setLevel(logging.INFO)


        for handler in logger.handlers[:]:
            logger.removeHandler(handler)


        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)


        formatter = logging.Formatter(f'%(asctime)s - Profile_{self.profile_id} - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.propagate = False

        self.logger = logger

    def load_processed_accounts(self):
        with self.lock:
            try:
                with open(self.used_accounts_file, 'r') as f:
                    return set(line.strip() for line in f)
            except FileNotFoundError:
                return set()

    def save_processed_account(self, api_key):
        with self.lock:
            try:
                with open(self.used_accounts_file, 'a') as f:
                    f.write(api_key + '\n')
                self.processed_accounts.add(api_key)
                self.logger.info(f"Аккаунт {api_key[:10]}... сохранен как обработанный")
            except Exception as e:
                self.logger.error(f"Ошибка сохранения обработанного аккаунта: {e}")

    def parse_accounts_file(self):
        accounts = []
        try:
            with open(self.accounts_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if '|' in line:
                        api_key, _ = line.split('|')
                        api_key = api_key.strip()
                        if api_key not in self.processed_accounts:
                            accounts.append(api_key)
            self.logger.info(f"Найдено {len(accounts)} непроработанных аккаунтов")
            return accounts
        except Exception as e:
            self.logger.error(f"Ошибка чтения файла: {e}")
            return []

    def check_balance(self, api_key):
        try:
            url = f"{self.api_base}/balance?apikey={api_key}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                balance = response.json().get('balance', 0)
                self.logger.info(f"Баланс аккаунта {api_key[:10]}...: {balance}")
                return balance
            return 0
        except Exception as e:
            self.logger.error(f"Ошибка проверки баланса: {e}")
            return 0

    def check_stock(self):
        try:
            url = f"{self.api_base}/instock"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            self.logger.error(f"Ошибка проверки стока: {e}")
            return {}

    def buy_email(self, api_key, domain="outlook"):
        try:
            url = f"{self.api_base}/buy?mail_domain={domain}&quantity=1&apikey={api_key}&format=1"
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            self.logger.error(f"Ошибка покупки email: {e}")
            return None

    def clear_browser_data(self, driver):
        try:
            self.logger.info("Очищаем данные браузера...")

            driver.delete_all_cookies()

            driver.execute_script("window.localStorage.clear();")
            driver.execute_script("window.sessionStorage.clear();")

            driver.execute_script("""
                if (window.indexedDB) {
                    indexedDB.databases().then(function(databases) {
                        for (let db of databases) {
                            indexedDB.deleteDatabase(db.name);
                        }
                    });
                }
            """)

            self.logger.info("Данные браузера очищены")
        except Exception as e:
            self.logger.error(f"Ошибка очистки данных браузера: {e}")

    def setup_driver(self, clear_profile=False):
        chrome_options = Options()

        profile_path = f"/home/kul1ght/Desktop/Higgsfield/chrome_profile_{self.profile_id}"

        if clear_profile and os.path.exists(profile_path):
            try:
                shutil.rmtree(profile_path)
                self.logger.info(f"Профиль {profile_path} очищен")
            except Exception as e:
                self.logger.error(f"Ошибка очистки профиля: {e}")

        chrome_options.add_argument(f"--user-data-dir={profile_path}")

        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-debugging-port=0")

        chrome_options.add_argument("--disable-application-cache")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")

        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        try:
            os.makedirs(profile_path, exist_ok=True)

            driver = webdriver.Chrome(options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            driver.set_window_size(1200, 800)

            self.driver = driver
            self.logger.info(f"Драйвер запущен с профилем {self.profile_id}")
            return driver
        except Exception as e:
            self.logger.error(f"Ошибка создания драйвера: {e}")
            return None

    def is_browser_alive(self, driver):
        try:
            driver.current_url
            return True
        except WebDriverException:
            return False

    def safe_find_elements(self, driver, by, value):
        if not self.is_browser_alive(driver):
            raise WebDriverException("Браузер закрыт")

        try:
            return driver.find_elements(by, value)
        except WebDriverException as e:
            if "invalid session id" in str(e).lower() or "browser has closed" in str(e).lower():
                raise WebDriverException("Браузер закрыт")
            raise e

    def safe_get_url(self, driver):
        if not self.is_browser_alive(driver):
            raise WebDriverException("Браузер закрыт")

        try:
            return driver.current_url
        except WebDriverException as e:
            if "invalid session id" in str(e).lower() or "browser has closed" in str(e).lower():
                raise WebDriverException("Браузер закрыт")
            raise e

    def higgsfield_signup_process(self, driver, email, password):
        try:
            self.logger.info("Начинаем процесс регистрации...")

            driver.execute_script("window.open('');")
            driver.switch_to.window(driver.window_handles[-1])
            driver.get("https://higgsfield.ai")
            time.sleep(3)

            signup_btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, '/auth') and contains(text(), 'Sign up')]"))
            )
            signup_btn.click()
            self.logger.info("Нажата кнопка Sign up")
            time.sleep(3)

            microsoft_btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Continue with Microsoft')]"))
            )
            microsoft_btn.click()
            self.logger.info("Нажата кнопка Microsoft")
            time.sleep(3)

            email_input = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='email']"))
            )
            email_input.clear()
            email_input.send_keys(email)
            self.logger.info("Введен email")

            next_btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Next']"))
            )
            next_btn.click()
            self.logger.info("Нажата кнопка Next после email")
            time.sleep(3)


            password_input = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='password']"))
            )
            password_input.clear()
            password_input.send_keys(password)
            self.logger.info("Введен пароль")

            # Шаг 7: Кнопка Next после пароля
            submit_btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and contains(., 'Next')]"))
            )
            submit_btn.click()
            self.logger.info("Нажата кнопка Next после пароля")
            time.sleep(3)
            try:
                yes_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and contains(., 'Yes')]"))
                )
                yes_btn.click()
                self.logger.info("Нажата кнопка Yes")
                time.sleep(3)
            except TimeoutException:
                self.logger.info("Кнопка Yes не найдена, пропускаем")

            try:
                accept_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept')]"))
                )
                accept_btn.click()
                self.logger.info("Нажата кнопка Accept")
                time.sleep(3)
            except TimeoutException:
                self.logger.info("Кнопка Accept не найдена, пропускаем")

            WebDriverWait(driver, 20).until(
                EC.url_contains("higgsfield")
            )

            self.logger.info("✓ Успешный вход в аккаунт!")
            return True

        except WebDriverException as e:
            if "browser has closed" in str(e).lower() or "invalid session id" in str(e).lower():
                self.logger.info("Браузер был закрыт во время регистрации")
                return False
            self.logger.error(f"Ошибка в процессе регистрации: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка в процессе регистрации: {e}")
            return False

    def wait_for_manual_generate(self, driver, api_key, email):
        self.logger.info("Ожидаем ручного нажатия кнопки Generate...")
        self.logger.info("Инструкция:")
        self.logger.info("1. Перейдите на https://higgsfield.ai/create/video")
        self.logger.info("2. Настройте параметры видео")
        self.logger.info("3. Нажмите кнопку Generate")
        self.logger.info("4. Софт начнет мониторинг генерации")
        self.logger.info("5. Когда закончите, закройте браузер чтобы перейти к следующему аккаунту")

        generate_clicked = False

        while not generate_clicked:
            try:
                if not self.is_browser_alive(driver):
                    self.logger.info("Браузер закрыт пользователем")
                    return False

                current_url = self.safe_get_url(driver)
                if "create/video" in current_url:
                    generate_buttons = self.safe_find_elements(driver, By.XPATH,
                        "//button[contains(., 'Generate') and contains(@class, 'bg-primary')]")

                    if generate_buttons:
                        generate_button = generate_buttons[0]
                        is_disabled = generate_button.get_attribute("disabled")

                        if is_disabled:
                            generate_clicked = True
                            self.logger.info("✓ Кнопка Generate нажата! Начинаем мониторинг...")
                            self.monitor_generation(driver, api_key, email)
                            break

                time.sleep(5)

            except WebDriverException as e:
                if "browser has closed" in str(e).lower() or "invalid session id" in str(e).lower():
                    self.logger.info("Браузер закрыт во время ожидания Generate")
                    return False
                self.logger.error(f"Ошибка ожидания Generate: {e}")
                time.sleep(10)
            except Exception as e:
                self.logger.error(f"Ошибка ожидания Generate: {e}")
                time.sleep(10)

        return generate_clicked

    def monitor_generation(self, driver, api_key, email):
        self.logger.info("🚀 Начинаем мониторинг генерации...")

        start_time = datetime.now()
        monitoring_count = 0

        try:
            while True:
                if not self.is_browser_alive(driver):
                    self.logger.info("Браузер закрыт, прекращаем мониторинг")
                    break


                monitoring_data = self.collect_monitoring_data(driver, api_key, email, start_time, monitoring_count)
                self.save_monitoring_data(monitoring_data)

                generate_buttons = self.safe_find_elements(driver, By.XPATH,
                    "//button[contains(., 'Generate') and contains(@class, 'bg-primary')]")

                if generate_buttons:
                    generate_button = generate_buttons[0]
                    is_disabled = generate_button.get_attribute("disabled")

                    if not is_disabled:
                        self.logger.info("✓ Генерация завершена!")
                        time.sleep(10)
                        break

                monitoring_count += 1
                time.sleep(10)

        except WebDriverException as e:
            if "browser has closed" in str(e).lower() or "invalid session id" in str(e).lower():
                self.logger.info("Браузер закрыт во время мониторинга")
            else:
                self.logger.error(f"Ошибка мониторинга: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка мониторинга: {e}")

        self.logger.info("Мониторинг завершен")

    def collect_monitoring_data(self, driver, api_key, email, start_time, count):
        try:
            current_time = datetime.now()
            current_url = self.safe_get_url(driver)

            network_logs = self.get_network_logs(driver)

            video_elements = self.safe_find_elements(driver, By.XPATH, "//*[contains(text(), 'video') or contains(@class, 'video')]")
            progress_elements = self.safe_find_elements(driver, By.XPATH, "//*[contains(text(), '%') or contains(@class, 'progress')]")

            progress_indicators = []
            for elem in progress_elements:
                try:
                    text = elem.text.strip()
                    if text:
                        progress_indicators.append(text)
                except:
                    pass

            monitoring_data = {
                'timestamp': current_time.isoformat(),
                'api_key': api_key,
                'email': email,
                'profile_id': self.profile_id,
                'monitoring_count': count,
                'url': current_url,
                'generation_time_seconds': (current_time - start_time).total_seconds(),
                'video_elements_count': len(video_elements),
                'progress_indicators': progress_indicators,
                'network_requests_count': len(network_logs),
                'video_related_requests': len([log for log in network_logs if 'video' in log.get('url', '').lower()])
            }

            return monitoring_data

        except WebDriverException as e:
            if "browser has closed" in str(e).lower() or "invalid session id" in str(e).lower():
                raise e
            return {
                'timestamp': datetime.now().isoformat(),
                'api_key': api_key,
                'email': email,
                'profile_id': self.profile_id,
                'error': str(e)
            }
        except Exception as e:
            return {
                'timestamp': datetime.now().isoformat(),
                'api_key': api_key,
                'email': email,
                'profile_id': self.profile_id,
                'error': str(e)
            }

    def get_network_logs(self, driver):
        try:
            if not self.is_browser_alive(driver):
                return []

            logs = driver.get_log('performance')
            network_logs = []

            for log in logs:
                try:
                    message = json.loads(log['message'])['message']
                    if message['method'] == 'Network.requestWillBeSent':
                        request = message['params']['request']
                        network_logs.append({
                            'url': request.get('url', ''),
                            'method': request.get('method', '')
                        })
                except:
                    continue

            return network_logs
        except WebDriverException:
            return []
        except:
            return []

    def save_monitoring_data(self, monitoring_data):
        try:
            with open(self.results_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(monitoring_data, ensure_ascii=False) + '\n')

            if 'error' not in monitoring_data:
                self.logger.info(f"Мониторинг #{monitoring_data['monitoring_count']}: "
                               f"{monitoring_data['generation_time_seconds']:.1f}с, "
                               f"{monitoring_data['video_related_requests']} видео-запросов")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения данных: {e}")

    def safe_quit_driver(self, driver):
        try:
            if driver and self.is_browser_alive(driver):
                self.clear_browser_data(driver)

                for handle in driver.window_handles:
                    driver.switch_to.window(handle)
                    driver.close()
                    time.sleep(1)

                driver.quit()
                self.logger.info("Браузер закрыт и данные очищены")
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии браузера: {e}")

    def process_single_account(self, api_key):
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"Профиль {self.profile_id} обрабатывает аккаунт: {api_key}")
        self.logger.info(f"{'='*60}")

        balance = self.check_balance(api_key)
        if balance == 0:
            self.logger.info("Баланс равен 0, пропускаем аккаунт")
            self.save_processed_account(api_key)
            return False

        stock = self.check_stock()
        if not stock:
            self.logger.error("Нет доступных почт!")
            return False

        domain = "outlook" if "outlook.com" in stock else "hotmail"
        email_data = self.buy_email(api_key, domain)
        if not email_data:
            self.logger.error("Не удалось купить email")
            return False

        email_info = email_data[0]
        email = email_info['email']
        password = email_info['password']

        self.logger.info(f"✓ Получены данные: {email}")

        driver = self.setup_driver(clear_profile=True)
        if not driver:
            self.logger.error("Не удалось создать драйвер")
            return False

        success = False

        try:
            if self.higgsfield_signup_process(driver, email, password):
                self.logger.info("✓ Регистрация успешна!")

                if self.wait_for_manual_generate(driver, api_key, email):
                    success = True
                else:
                    self.logger.info("Пользователь закрыл браузер или время истекло")
            else:
                self.logger.error("Не удалось завершить регистрацию")

        except WebDriverException as e:
            if "browser has closed" in str(e).lower():
                self.logger.info("Браузер был закрыт пользователем")
            else:
                self.logger.error(f"Ошибка WebDriver при обработке аккаунта: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка обработки аккаунта: {e}")
        finally:
            self.safe_quit_driver(driver)

        self.save_processed_account(api_key)
        return success

    def run_continuous_processing(self):
        self.logger.info(f"🚀 Профиль {self.profile_id} запускает обработку аккаунтов")

        while True:
            accounts = self.parse_accounts_file()

            if not accounts:
                self.logger.info("Все аккаунты обработаны! Ожидаем новых аккаунтов...")
                time.sleep(60)
                continue

            self.logger.info(f"Найдено {len(accounts)} аккаунтов для обработки")

            for i, api_key in enumerate(accounts, 1):
                self.logger.info(f"\n📦 Профиль {self.profile_id} обрабатывает аккаунт {i}/{len(accounts)}")

                try:
                    success = self.process_single_account(api_key)

                    if success:
                        self.logger.info("✓ Аккаунт успешно обработан")
                    else:
                        self.logger.info("✗ Ошибка обработки аккаунта")

                except KeyboardInterrupt:
                    self.logger.info("Обработка прервана пользователем")
                    return
                except Exception as e:
                    self.logger.error(f"Критическая ошибка при обработке аккаунта: {e}")
                    continue

    def display_stats(self):
        try:
            with open(self.used_accounts_file, 'r') as f:
                used_count = len(f.readlines())

            accounts = self.parse_accounts_file()
            total_count = len(accounts) + used_count

            self.logger.info(f"\n📊 Статистика профиля {self.profile_id}:")
            self.logger.info(f"Всего аккаунтов: {total_count}")
            self.logger.info(f"Обработано: {used_count}")
            self.logger.info(f"Осталось: {len(accounts)}")

        except Exception as e:
            self.logger.error(f"Ошибка получения статистики: {e}")

def run_profile(profile_id):
    monitor = HiggsfieldMultiAccountMonitor(profile_id)

    print(f"🚀 Higgsfield Multi-Account Auto Monitor - Профиль {profile_id}")
    print("=" * 60)
    print("Особенности:")
    print("- Автоматически перебирает все аккаунты из файла")
    print("- Пропускает аккаунты с балансом 0")
    print("- Полная очистка сессий между аккаунтами")
    print("- Работает пока не закончатся аккаунты или не будет остановлен")
    print("=" * 60)

    monitor.display_stats()

    try:
        monitor.run_continuous_processing()
    except KeyboardInterrupt:
        monitor.logger.info(f"Профиль {profile_id} остановлен пользователем")
    except Exception as e:
        monitor.logger.error(f"Критическая ошибка в профиле {profile_id}: {e}")
    finally:
        monitor.logger.info(f"Работа профиля {profile_id} завершена")

def main():
    print("🚀 Higgsfield Multi-Account Auto Monitor - 3 ПРОФИЛЯ")
    print("=" * 60)
    print("Запускаем 3 параллельных профиля...")
    print("Каждый профиль будет работать в своем окне браузера")
    print("Полная очистка сессий между аккаунтами гарантирована!")
    print("=" * 60)

    with ThreadPoolExecutor(max_workers=3) as executor: ##############################################
        futures = [executor.submit(run_profile, i) for i in range(3)]

        try:
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Ошибка в профиле: {e}")
        except KeyboardInterrupt:
            print("Все профили остановлены пользователем")
            executor.shutdown(wait=False)

if __name__ == "__main__":
    main()
