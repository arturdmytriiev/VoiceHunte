from __future__ import annotations

from app.agent.models import AgentResponse, Intent
from app.agent.state import CallState


_LANGUAGE_PROMPTS = {
    "en": {
        "missing_name": "Could you share the name for the reservation?",
        "missing_datetime": "What date and time should we book?",
        "missing_people": "How many people will be attending?",
        "missing_reservation_id": "Please provide the reservation ID.",
        "generic": "How can I help you today?",
        "hours": "We are open daily from 10:00 to 22:00.",
        "menu_empty": "I can help with the menu. What are you interested in?",
        "created": "Reservation created.",
        "updated": "Reservation updated.",
        "cancelled": "Reservation cancelled.",
    },
    "ru": {
        "missing_name": "Подскажите, на какое имя оформить бронь?",
        "missing_datetime": "На какую дату и время оформить бронь?",
        "missing_people": "Сколько человек будет?",
        "missing_reservation_id": "Назовите номер брони, пожалуйста.",
        "generic": "Чем могу помочь?",
        "hours": "Мы работаем ежедневно с 10:00 до 22:00.",
        "menu_empty": "Могу рассказать про меню. Что вас интересует?",
        "created": "Бронь создана.",
        "updated": "Бронь обновлена.",
        "cancelled": "Бронь отменена.",
    },
    "uk": {
        "missing_name": "Підкажіть, на чиє ім'я оформити бронювання?",
        "missing_datetime": "На яку дату та час зробити бронювання?",
        "missing_people": "Скільки людей буде?",
        "missing_reservation_id": "Повідомте номер бронювання, будь ласка.",
        "generic": "Чим можу допомогти?",
        "hours": "Ми працюємо щодня з 10:00 до 22:00.",
        "menu_empty": "Можу підказати по меню. Що саме цікавить?",
        "created": "Бронювання створено.",
        "updated": "Бронювання оновлено.",
        "cancelled": "Бронювання скасовано.",
    },
    "sk": {
        "missing_name": "Na aké meno mám rezerváciu vytvoriť?",
        "missing_datetime": "Na aký dátum a čas to má byť?",
        "missing_people": "Pre koľko osôb bude rezervácia?",
        "missing_reservation_id": "Prosím, uveďte ID rezervácie.",
        "generic": "Ako vám môžem pomôcť?",
        "hours": "Máme otvorené denne od 10:00 do 22:00.",
        "menu_empty": "Môžem pomôcť s menu. Čo vás zaujíma?",
        "created": "Rezervácia bola vytvorená.",
        "updated": "Rezervácia bola upravená.",
        "cancelled": "Rezervácia bola zrušená.",
    },
}


def _prompts(language: str) -> dict[str, str]:
    return _LANGUAGE_PROMPTS.get(language, _LANGUAGE_PROMPTS["en"])


def respond(state: CallState) -> CallState:
    language = state.language or "en"
    prompts = _prompts(language)
    intent = state.intent
    entities = state.entities
    answer_text = prompts["generic"]
    actions: list[str] = []

    if intent == Intent.hours_info:
        answer_text = prompts["hours"]
    elif intent == Intent.menu_question:
        menu_results = next(
            (
                result.payload.get("items", [])
                for result in state.tool_results
                if result.tool == "menu_context"
            ),
            [],
        )
        if not menu_results:
            answer_text = prompts["menu_empty"]
        else:
            summarized = ", ".join(
                f"{item.get('name')} ({item.get('price')})"
                for item in menu_results
                if item.get("name")
            )
            answer_text = summarized or prompts["menu_empty"]
    elif intent == Intent.create_reservation:
        missing_fields = []
        if not entities or not entities.name:
            missing_fields.append(prompts["missing_name"])
        if not entities or not entities.datetime:
            missing_fields.append(prompts["missing_datetime"])
        if not entities or not entities.people:
            missing_fields.append(prompts["missing_people"])
        if missing_fields:
            answer_text = " ".join(missing_fields)
            actions.append("clarify")
        else:
            answer_text = prompts["created"]
    elif intent == Intent.update_reservation:
        if not entities or not entities.reservation_id:
            answer_text = prompts["missing_reservation_id"]
            actions.append("clarify")
        else:
            answer_text = prompts["updated"]
    elif intent == Intent.cancel_reservation:
        if not entities or not entities.reservation_id:
            answer_text = prompts["missing_reservation_id"]
            actions.append("clarify")
        else:
            answer_text = prompts["cancelled"]

    state.final_answer = AgentResponse(
        answer_text=answer_text,
        actions=actions,
        language=language,
    )
    return state
