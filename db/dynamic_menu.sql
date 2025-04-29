-- -------------------------------------------------------------
-- TablePlus 6.4.4(604)
--
-- https://tableplus.com/
--
-- Database: astrolog
-- Generation Time: 2025-04-29 22:01:01.3720
-- -------------------------------------------------------------


-- This script only contains the table creation statements and does not fully represent the table in the database. Do not use it as a backup.

-- Table Definition
CREATE TABLE "public"."dynamic_menu" (
    "id" int8,
    "button_name" text,
    "button_action" text,
    "position" int8,
    "chain_id" int8,
    "menu_chain_id" int8
);

INSERT INTO "public"."dynamic_menu" ("id", "button_name", "button_action", "position", "chain_id", "menu_chain_id") VALUES
(1, 'Прогноз на встречу', 'Прогноз на встречу', 1, 1, 3),
(4, 'Совместимость в любви', 'Совместимость в любви', 1, 11, 2),
(5, 'Совместимость в дружбе', 'Совместимость в дружбе', 1, 12, 2),
(6, 'Свой портрет', 'Свой портрет', 1, 14, 4);
