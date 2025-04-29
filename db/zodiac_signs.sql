-- -------------------------------------------------------------
-- TablePlus 6.4.4(604)
--
-- https://tableplus.com/
--
-- Database: astrolog
-- Generation Time: 2025-04-29 22:03:04.2320
-- -------------------------------------------------------------


-- This script only contains the table creation statements and does not fully represent the table in the database. Do not use it as a backup.

-- Sequence and defined type
CREATE SEQUENCE IF NOT EXISTS zodiac_signs_id_seq;

-- Table Definition
CREATE TABLE "public"."zodiac_signs" (
    "id" int4 NOT NULL DEFAULT nextval('zodiac_signs_id_seq'::regclass),
    "cutoff_date" int4 NOT NULL,
    "name" text NOT NULL,
    PRIMARY KEY ("id")
);

INSERT INTO "public"."zodiac_signs" ("id", "cutoff_date", "name") VALUES
(1, 120, 'Козерог'),
(2, 218, 'Водолей'),
(3, 320, 'Рыбы'),
(4, 420, 'Овен'),
(5, 521, 'Телец'),
(6, 621, 'Близнецы'),
(7, 722, 'Рак'),
(8, 823, 'Лев'),
(9, 923, 'Дева'),
(10, 1023, 'Весы'),
(11, 1122, 'Скорпион'),
(12, 1222, 'Стрелец'),
(13, 1231, 'Козерог');
