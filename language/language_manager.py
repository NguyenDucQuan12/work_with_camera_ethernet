import json
import logging

logger = logging.getLogger(__name__)

json_filename = "src/language/language_manager.json"
with open(json_filename, 'r') as inside:
    data = json.load(inside)

    language = data['language']

class LanguageLoader:
    def __init__(self, language="Vietnamese"):
        self.language = language
        self.lang_dict = {}
        self.load_language(language= self.language)

    def load_language(self, language):
        """
        Load ngôn ngữ từ tệp JSON
        """
        try:
            with open(f'src/language/{language}/language.json', 'r', encoding='utf-8') as f:
                self.lang_dict = json.load(f)
        except FileNotFoundError:
            logger.warning(f"Ngôn ngữ {language} không tồn tại, sử dụng tiếng Việt mặc định.")
            with open('src/language/Vietnamese/language.json', 'r', encoding='utf-8') as f:
                self.lang_dict = json.load(f)

    # def change_language_to_japanese(self, language):
    #     self.load_language(language= language)

    def get_text(self, text_key):
        """
        Lấy giá trị chuỗi dựa trên từ khóa ngôn ngữ.  
        Nếu giá trị `key` không tồn tại thì thông báo
        """
        # Nếu key là kiểu lồng nhau (nested), lấy giá trị phù hợp
        keys = text_key.split('.')
        result = self.lang_dict
        try:
            for key in keys:
                result = result[key]
            return result
        except KeyError:
            return f"{text_key} không tồn tại trong ngôn ngữ {self.language}"

# Khởi tạo hệ thống ngôn ngữ
language_system = LanguageLoader(language= language)

# Ví dụ sử dụng
if __name__ == "__main__":
    
    language_system.load_language(language= "Japanese")
    print(language_system.get_text('camera.error_read_frame'))  # Sẽ xuất ra chuỗi tương ứng với tiếng Nhật