-- MNS - Medical Notification System
-- Schema for the user system.
--
-- Run with:  sudo mysql < query.sql
-- (see README for the full setup steps)

CREATE DATABASE IF NOT EXISTS MNS
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE MNS;

-- Named `users` (plural) because USER is a built-in function name in MySQL.
CREATE TABLE IF NOT EXISTS users
(
    id            INT AUTO_INCREMENT PRIMARY KEY,

    -- login credentials
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(60)  NOT NULL,  -- bcrypt output is always 60 chars

    -- profile
    name          VARCHAR(40)  NOT NULL,
    surname       VARCHAR(40)  NOT NULL,
    birth_date    DATE         NOT NULL,
    address       VARCHAR(50)  NOT NULL,
    city          VARCHAR(20)  NOT NULL,
    country       VARCHAR(20)  NOT NULL,

    -- for the SMS notifications in the README; optional at signup
    phone         VARCHAR(20)  NULL,

    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;
