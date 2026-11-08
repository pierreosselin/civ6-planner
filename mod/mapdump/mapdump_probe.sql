-- Harmless marker showing the game loads files from this mod (visible in Cache/DebugGameplay.sqlite).
CREATE TABLE IF NOT EXISTS MapDumpProbe (Loaded TEXT);
INSERT INTO MapDumpProbe (Loaded) VALUES ('yes');
