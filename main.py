import os
import telebot
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types

load_dotenv()
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = "models/gemini-2.5-flash"

user_modes = {}

# --- LANGUAGE CONFIG ---

LANG_CONFIG = {
    "Dutch": {
        "flag": "🇳🇱",
        "pronouns": ["ik", "jij/je", "hij/zij/het", "wij/we", "jullie", "zij/ze"],
        "tenses": "Present, Simple Past (Verleden tijd), Conditional, Future",
        "example_tenses": ["Simple Past", "Future", "Conditional"],
        "tense_note": "Note: Dutch has no separate imperfect — Simple Past covers both.",
    },
    "Spanish": {
        "flag": "🇪🇸",
        "pronouns": ["yo", "tu", "el/ella/Ud.", "nosotros", "vosotros", "ellos/Uds."],
        "tenses": "Present, Preterite, Imperfect, Conditional, Future",
        "example_tenses": ["Preterite", "Future", "Conditional"],
        "tense_note": "",
    },
    "German": {
        "flag": "🇩🇪",
        "pronouns": ["ich", "du", "er/sie/es", "wir", "ihr", "sie/Sie"],
        "tenses": "Present, Preterite, Imperfect, Conditional, Future",
        "example_tenses": ["Imperfect", "Future", "Conditional"],
        "tense_note": "",
    },
}

SUPPORTED_LANGS = list(LANG_CONFIG.keys())

# --- HISTORY ---

def save_to_history(chat_id, text):
    with open(f"history_{chat_id}.txt", "a", encoding="utf-8") as f:
        f.write(text + "\n")

def get_history(chat_id):
    path = f"history_{chat_id}.txt"
    return open(path, encoding="utf-8").read() if os.path.exists(path) else "No history yet."

# --- LANGUAGE DETECTION ---

def detect_language_from_text(text):
    prompt = f"Identify the language of this sentence. Reply with exactly one word: Dutch, Spanish, or German.\nSentence: {text}"
    r = client.models.generate_content(model=MODEL_NAME, contents=prompt)
    detected = r.text.strip().split()[0].capitalize()
    return detected if detected in SUPPORTED_LANGS else None

def detect_language_from_image(image_bytes):
    prompt = "What language is the text in this image? Reply with exactly one word: Dutch, Spanish, or German."
    part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
    r = client.models.generate_content(model=MODEL_NAME, contents=[prompt, part])
    detected = r.text.strip().split()[0].capitalize()
    return detected if detected in SUPPORTED_LANGS else None

# --- PROMPT BUILDERS ---

LANGUAGE_POINT_RULES = """
[Number each point. Put a blank line between each point. Short and concise.
Rules per word type:
- Skip: the word, standalone articles and obvious words with no notable grammar role.
- Adjective: the word, adjective(term in target language), meaning. One line on ending rule if relevant.
- Noun: the word, meaning. singular - plural.
- Preposition (only with notable usage): the word, meaning. Brief note on usage.
- Verb:  the word, 2-3 sentences. Add one short simple example sentence.
- Verb phrase (Fixed/reflexive/separable verb phrase): the word, 2-3 sentences. Add one short simple example sentence.
]
"""

def conjugation_instruction(lang):
    cfg = LANG_CONFIG[lang]
    pronoun_lines = "\n".join(f"▪ {p}, ..." for p in cfg["pronouns"])
    tense_examples = ", ".join(cfg["example_tenses"])
    note = f"\n[{cfg['tense_note']}]" if cfg["tense_note"] else ""

    return f"""
🔀 Conjugation: [infinitive of the BASE verb only — not the full phrase]
[If the verb is separable or reflexive, conjugate only the core verb. E.g. for "zich inzetten voor" use "inzetten"; for "jugar al golf" use "jugar".]{note}

[Header line:]
Pronoun, {cfg['tenses']}

[One line per pronoun — use ONLY these exact pronouns in this exact order, each starting with ▪:]
{pronoun_lines}

[After the table, write exactly 3 example sentences.]
[Rewrite the ORIGINAL sentence in a different tense. Keep the same subject, object, and meaning — only change the tense.]
[Tenses to use: {tense_examples}.]
[Tense]:
[sentence in {lang}]
[English translation]
"""

def build_analysis_prompt(lang, flag, sentence):
    """Single prompt used for both text and image analysis."""
    cfg = LANG_CONFIG[lang]
    return f"""
You are a {lang} language tutor. Analyze this {lang} sentence.

The sentence is in {lang}. Analyze it as {lang}. Do NOT translate it to another language.

Reply in this exact format:

{flag} {sentence}

🇬🇧 [English translation]

📝 Language points:
{LANGUAGE_POINT_RULES}

{conjugation_instruction(lang)}

STRICT RULES:
- The first line of your reply MUST be exactly: {flag} {sentence}
- Analyze the sentence as {lang}. Do not convert it to Dutch or any other language.
- All explanations in English.
- No bold, italic, or Markdown (no *, **, _, __, |, backticks).
- Conjugation rows: comma-separated, start each with ▪, use ONLY the {lang} pronouns: {", ".join(cfg["pronouns"])}
- Blank line between each language point and between each section.
"""

def build_test_prompt(lang, history):
    return f"""
You are a {lang} language tutor. Create a short quiz from these studied sentences:
{history}

Generate exactly:
1. Two fill-in-the-blank questions (replace one key word with ______).
   Next line: Answer: [word]

2. One article challenge using a noun from the sentences.
   [Choose from the following]
   Dutch:   ___ (de/het) [noun]
   Spanish: ___ (el/la) [noun]
   German:  ___ (der/die/das) [noun]
   Next line: Answer: [article] [noun]

Plain English instructions only. No bold, italic, or Markdown.
"""

# --- HANDLERS ---

@bot.message_handler(commands=['start', 'dutch', 'spanish', 'german'])
def set_language(message):
    lang_map = {'dutch': 'Dutch', 'spanish': 'Spanish', 'german': 'German'}
    lang = next((v for k, v in lang_map.items() if k in message.text.lower()), 'Dutch')
    user_modes[message.chat.id] = lang
    flag = LANG_CONFIG[lang]['flag']
    bot.reply_to(message, f"{flag} Language set to {lang}.\nSend 'Learn: [sentence]' or an image to start!")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("test"))
def handle_test(message):
    chat_id = message.chat.id
    lang = user_modes.get(chat_id, "Dutch")
    response = client.models.generate_content(model=MODEL_NAME, contents=build_test_prompt(lang, get_history(chat_id)))
    bot.reply_to(message, response.text)

@bot.message_handler(content_types=['photo', 'text'])
def handle_learning(message):
    chat_id = message.chat.id
    is_image = message.content_type == 'photo'

    try:
        bot.send_chat_action(chat_id, 'typing')

        if is_image:
            file_info = bot.get_file(message.photo[-1].file_id)
            image_bytes = bot.download_file(file_info.file_path)

            # Step 1: detect language from image first
            lang = detect_language_from_image(image_bytes)
            if not lang:
                lang = user_modes.get(chat_id, "Dutch")
            flag = LANG_CONFIG[lang]["flag"]

            # Step 2: extract text from image
            extract_prompt = f"Extract the {lang} text from this image. Reply with only the extracted text, nothing else."
            part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
            extract_response = client.models.generate_content(model=MODEL_NAME, contents=[extract_prompt, part])
            extracted_text = extract_response.text.strip()

            # Step 3: analyze with correct language config
            content_list = [build_analysis_prompt(lang, flag, extracted_text)]

        else:
            if not message.text.lower().startswith("learn:"):
                return
            user_text = message.text[6:].strip()

            # Detect language from the sentence
            lang = detect_language_from_text(user_text)
            if not lang:
                lang = user_modes.get(chat_id, "Dutch")
            flag = LANG_CONFIG[lang]["flag"]

            save_to_history(chat_id, user_text)
            content_list = [build_analysis_prompt(lang, flag, user_text)]

        response = client.models.generate_content(model=MODEL_NAME, contents=content_list)
        bot.reply_to(message, response.text)

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, "Error processing the request. Check the VS Code console.")

if __name__ == "__main__":
    print("Language Tutor Bot is Online...")
    bot.infinity_polling()
