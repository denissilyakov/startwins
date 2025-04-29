-- -------------------------------------------------------------
-- TablePlus 6.4.4(604)
--
-- https://tableplus.com/
--
-- Database: astrolog
-- Generation Time: 2025-04-29 22:00:45.2120
-- -------------------------------------------------------------


-- This script only contains the table creation statements and does not fully represent the table in the database. Do not use it as a backup.

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS chinese_signs_id_seq;

-- Table Definition
CREATE TABLE "public"."chinese_signs" (
    "id" int4 NOT NULL DEFAULT nextval('chinese_signs_id_seq'::regclass),
    "name" text NOT NULL,
    PRIMARY KEY ("id")
);

INSERT INTO "public"."chinese_signs" ("id", "name") VALUES
(1, 'Крыса'),
(2, 'Бык'),
(3, 'Тигр'),
(4, 'Кролик'),
(5, 'Дракон'),
(6, 'Змея'),
(7, 'Лошадь'),
(8, 'Коза'),
(9, 'Обезьяна'),
(10, 'Петух'),
(11, 'Собака'),
(12, 'Свинья');
