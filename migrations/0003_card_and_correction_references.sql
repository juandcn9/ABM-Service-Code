ALTER TABLE movements ADD COLUMN merchant_reference TEXT CHECK (merchant_reference IS NULL OR (length(merchant_reference) BETWEEN 1 AND 128 AND merchant_reference NOT GLOB '*[^-A-Za-z0-9._~]*'));
ALTER TABLE movements ADD COLUMN decision_reference TEXT CHECK (decision_reference IS NULL OR (length(decision_reference) BETWEEN 1 AND 128 AND decision_reference NOT GLOB '*[^-A-Za-z0-9._~]*'));
