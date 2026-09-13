-- The three questions from the brief, against the schema in src/pipeline/load/sqlite.py (L4).
-- With one report loaded, the second and third return what the schema supports; they fill as reports are added.

-- name: top_enterprise_risks
-- "What are the top enterprise risks facing <company>, and how frequently are they reviewed at Board/Executive level?"
SELECT c.name AS company, r.fiscal_year, ri.title, ri.category, ri.page, ri.section,
       r.review_frequency, r.review_bodies
FROM risk_instance ri
JOIN report r ON r.id = ri.report_id
JOIN company c ON c.id = r.company_id
WHERE ri.source_register = 'erm_main_risk'
  AND (:company IS NULL OR c.id = :company OR lower(c.name) LIKE '%' || lower(:company) || '%')
  AND (:year IS NULL OR r.fiscal_year = :year)
ORDER BY r.fiscal_year DESC, ri.prominence, ri.page, ri.id;

-- name: newly_elevated_risks
-- "What emerging risks have been newly elevated?"
SELECT c.name AS company, s.fiscal_year, cr.canonical_title, s.status
FROM risk_status s
JOIN canonical_risk cr ON cr.id = s.canonical_risk_id
JOIN company c ON c.id = cr.company_id
WHERE s.status IN ('new', 'elevated')
  AND (:company IS NULL OR c.id = :company)
  AND (:year IS NULL OR s.fiscal_year = :year)
ORDER BY s.fiscal_year DESC, c.name, cr.canonical_title;

-- name: companies_with_category
-- "Show me every <sector> company that lists <category> as a principal risk"
SELECT DISTINCT c.name AS company, c.sector, r.fiscal_year, ri.title, ri.source_register, ri.page
FROM risk_instance ri
JOIN risk_category rc ON rc.risk_instance_id = ri.id
JOIN report r ON r.id = ri.report_id
JOIN company c ON c.id = r.company_id
WHERE rc.category = :category
  AND (:sector IS NULL OR lower(c.sector) LIKE '%' || lower(:sector) || '%')
  AND (:year IS NULL OR r.fiscal_year = :year)
ORDER BY c.name, r.fiscal_year DESC, ri.prominence;
