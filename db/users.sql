-- -------------------------------------------------------------
-- TablePlus 6.4.4(604)
--
-- https://tableplus.com/
--
-- Database: astrolog
-- Generation Time: 2025-04-29 22:02:42.8670
-- -------------------------------------------------------------


-- This script only contains the table creation statements and does not fully represent the table in the database. Do not use it as a backup.

-- Table Definition
CREATE TABLE "public"."users" (
    "user_id" int8 NOT NULL,
    "name" text,
    "birthdate" text,
    "gender" text,
    "zodiac" text,
    "chinese_year" text,
    "birthplace" text,
    "tz_offset" int8,
    "birthtime" text,
    "chat_id" int8,
    PRIMARY KEY ("user_id")
);

INSERT INTO "public"."users" ("user_id", "name", "birthdate", "gender", "zodiac", "chinese_year", "birthplace", "tz_offset", "birthtime", "chat_id") VALUES
(10581838, 'Денис', '14.02.1978', 'мужской', 'Водолей', 'Лошадь', 'Усть-Илимск, Иркутская область', 7, '12:00', 10581838),
(295988674, 'Виталик', '01.09.1999', 'мужской', 'Дева', 'Кролик', 'Иркутск', 7, '12:00', 295988674),
(519451234, 'Антон', '10.04.1996', 'мужской', 'Овен', 'Крыса', 'Самара', 5, '05:00', NULL),
(530354823, 'Jarik', '29.01.2004', 'мужской', 'Водолей', 'Обезьяна', 'Иркутск', 7, '23:30', NULL),
(1779838743, 'Магомед', '28.05.2008', 'мужской', 'Близнецы', 'Крыса', 'Брюссель', 2, '5:15', NULL),
(5292205759, 'Кристина', '15.02.1998', 'женский', 'Водолей', 'Тигр', 'Район сынджерей  республика Молдова', 7, '4:20', NULL);
