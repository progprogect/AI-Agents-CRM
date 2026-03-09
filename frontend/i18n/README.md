# Internationalization (i18n)

Локализация на базе [next-intl](https://next-intl.dev/). Язык хранится в cookie `NEXT_LOCALE`, без префикса в URL.

## Поддерживаемые языки

- `en` — English (по умолчанию)
- `ru` — Русский

## Добавление нового языка

1. Добавить код в `i18n/request.ts`:
   ```ts
   export const locales = ["en", "ru", "de"] as const;  // + de
   ```

2. Создать `messages/de.json` с той же структурой, что и `en.json`.

3. Перезапустить приложение.

## Добавление новых строк

1. Добавить ключ в `messages/en.json` и `messages/ru.json`.
2. Использовать в компоненте:
   ```tsx
   const t = useTranslations("Header");
   return <span>{t("newKey")}</span>;
   ```

## Структура сообщений

- `Header` — шапка админ-панели
- `Nav` — пункты бокового меню
- `Locale` — переключатель языка
- `Common` — общие кнопки и метки (Cancel, Loading, Actions и т.д.)
- `Status` — статусы разговоров (AI Responding, Needs Attention и т.д.)
- `Conversations` — страница списка разговоров
- `ConversationDetail` — страница деталей разговора
- `CRM` — страница CRM Pipeline
- `Stats` — страница статистики
- `Agents` — страница агентов (ключи добавлены, компоненты — по мере необходимости)
- `Login` — страница входа
