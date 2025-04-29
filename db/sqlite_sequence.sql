-- -------------------------------------------------------------
-- TablePlus 6.4.4(604)
--
-- https://tableplus.com/
--
-- Database: astrolog
-- Generation Time: 2025-04-29 22:02:21.9110
-- -------------------------------------------------------------


-- This script only contains the table creation statements and does not fully represent the table in the database. Do not use it as a backup.

-- Table Definition
CREATE TABLE "public"."sqlite_sequence" (
    "name" text,
    "seq" int8
);

INSERT INTO "public"."sqlite_sequence" ("name", "seq") VALUES
('question_chain_prompts', 8),
('menu_button_chain', 0),
('dynamic_menu', 7),
('user_conversations', 82),
('question_chains', 30);
