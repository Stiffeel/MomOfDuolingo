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

# --- HISTORY ---

def save_to_history(chat_id, text):
    with open(f"history_{chat_id}.txt", "a", encoding="utf-8") as f:
        f.write(text + "\n")

def get_history(chat_id):
    path = f"history_{chat_id}.txt"
    return open(path, encoding="utf-8").read() if os.path.exists(path) else "No history yet."

# --- CONJUGATION BLOCK BUILDER ---

def conjugation_instruction(lang):
    cfg = LANG_CONFIG[lang]
    pronoun_lines = "\n".join(f"▪ {p}, ..." for p in cfg["pronouns"])
    tense_examples = ", ".join(cfg["example_tenses"])
    note = f"\n[{cfg['tense_note']}]" if cfg["tense_note"] else ""

    return f"""
🔀 Conjugation: [infinitive of the BASE verb only — not the full phrase]
[If the verb is part of a separable or reflexive phrase, conjugate only the core verb.]
[Example: for "zich inzetten voor", conjugate only "inzetten". For "jugar al golf", conjugate only "jugar".]{note}

[Header line:]
Pronoun, {cfg['tenses']}

[Then one line per pronoun, starting with ▪:]
{pronoun_lines}

[After the table, write exactly 3 example sentences.]
[Take the ORIGINAL sentence and simply change the tense — keep the same subject, object, and meaning.]
[Do NOT invent a new sentence. Just rewrite the original in a different tense.]
[Tenses to use: {tense_examples}.]
[Format:]
[Tense]:
[{lang} sentence — original sentence rewritten in this tense]
[English translation]
"""

# --- PROMPT BUILDERS ---

LANGUAGE_POINT_RULES = """
[Number each point. Put a blank line between each point.
Rules per word type:
- Skip: standalone articles and obvious words with no notable grammar role.
- Adjective: adjective(term in target language), meaning. One line on ending rule if relevant.
- Noun: meaning. singular - plural.
- Preposition with notable usage: meaning. Brief note on usage.
- Fixed/reflexive/separable verb phrase: 2-3 sentences. Add one short simple example sentence.
]
"""

def build_learn_prompt(lang, flag, sentence):
    return f"""
You are a {lang} language tutor. Analyze the sentence and reply in this exact format:

{flag} {sentence}

🇬🇧 [English translation]

📝 Language points:
{LANGUAGE_POINT_RULES}

{conjugation_instruction(lang)}

STRICT RULES:
- English only for all explanations.
- No bold, italic, or Markdown (no *, **, _, __, |, backticks).
- Conjugation: comma-separated plain text rows, not pipe tables.
- Blank line between each language point.
- Blank line between each section.
"""

def build_image_prompt(lang, flag):
    return f"""
You are a {lang} language tutor.

Step 1: Extract the {lang} text from the image.
Step 2: Analyze it in this exact format:

{flag} [extracted sentence]

🇬🇧 [English translation]

📝 Language points:
{LANGUAGE_POINT_RULES}

{conjugation_instruction(lang)}

STRICT RULES:
- English only for all explanations.
- No bold, italic, or Markdown (no *, **, _, __, |, backticks).
- Conjugation: comma-separated plain text rows, not pipe tables.
- Blank line between each language point.
- Blank line between each section.
"""

def build_test_prompt(lang, history):
    return f"""
You are a {lang} language tutor. Create a short quiz from these studied sentences:
{history}

Generate exactly:
1. Two fill-in-the-blank questions (replace one key word with ______).
   Next line: Answer: [word]

2. One article challenge using a noun from the sentences.
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
    lang = user_modes.get(chat_id, "Dutch")
    flag = LANG_CONFIG[lang]["flag"]
    is_image = message.content_type == 'photo'

    try:
        bot.send_chat_action(chat_id, 'typing')

        if is_image:
            file_info = bot.get_file(message.photo[-1].file_id)
            data = bot.download_file(file_info.file_path)
            content_list = [
                build_image_prompt(lang, flag),
                genai_types.Part.from_bytes(data=data, mime_type="image/jpeg")
            ]
        else:
            if not message.text.lower().startswith("learn:"):
                return
            user_text = message.text[6:].strip()
            save_to_history(chat_id, user_text)
            content_list = [build_learn_prompt(lang, flag, user_text)]

        response = client.models.generate_content(model=MODEL_NAME, contents=content_list)
        bot.reply_to(message, response.text)

    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, "Error processing the request. Check the VS Code console.")

if __name__ == "__main__":
    print("Language Tutor Bot is Online...")
    bot.infinity_polling()