"""Seed data: budget lines from the Hasolidit sheet, sector→line mapping and generic rules.

Only generic, non-personal patterns live here. Personal rules (employer names etc.)
are added from the Settings page and stay in the local DB.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import INTERNAL_TRANSFER, UNCATEGORIZED, BudgetLine, CategoryRule, SectorMap

# Bank-side lines that are shown on the bank page but not counted in the income & expenses sheet:
# securities buys/sells move money between own assets, and card payoffs are already counted per card transaction.
SECURITIES_LINE = "ניירות ערך"
CARD_PAYOFF_LINE = "אשראי"

# (group, name, personal-inflation group) — order as in "מעקב הכנסות והוצאות"
BUDGET_LINES = [
    ("income", "שכר עבודה #1 - נטו", ""),
    ("income", "שכר עבודה #2 - נטו", ""),
    ("income", "הכנסה מעסק - נטו", ""),
    ("income", "ריבית ודיבידנדים - נטו", ""),
    ("income", "הכנסה משכירות - נטו", ""),
    ("income", "קצבאות / מלגות", ""),
    ("income", "הכנסה אחרת / חד פעמית", ""),
    ("need_fixed", "משכנתא / דמי שכירות", "דיור"),
    ("need_fixed", "ארנונה (חודשית)", "תחזוקת הדירה"),
    ("need_fixed", "ועד בית", "תחזוקת הדירה"),
    ("need_fixed", 'ביטוח רפואי (כולל קופ"ח)', "בריאות"),
    ("need_fixed", "הוצאות תחבורה ציבורית ואופניים", "תחבורה ותקשורת"),
    ("need_fixed", "שמרטפים למיניהם (גני ילדים, צהרנים ועוד)", "חינוך, תרבות ובידור"),
    ("need_fixed", "ביטוח דירה", "תחזוקת הדירה"),
    ("need_fixed", "החזרי הלוואות", "שונות"),
    ("need_fixed", "הוצאה חיונית חוזרת אחרת", "שונות"),
    ("need_variable", "מצרכי מזון", "מזון"),
    ("need_variable", "תרופות, בדיקות וטיפולים רפואיים", "בריאות"),
    ("need_variable", "מוצרי היגיינה", "שונות"),
    ("need_variable", "חשבון חשמל", "תחזוקת הדירה"),
    ("need_variable", "חשבון גז", "תחזוקת הדירה"),
    ("need_variable", "חשבון מים וביוב", "תחזוקת הדירה"),
    ("need_variable", "חשבון טלפון עיקרי", "תחבורה ותקשורת"),
    ("need_variable", "עמלות שירות ובירוקרטיה", "שונות"),
    ("need_variable", "משיכת כספים (כספומט)", "שונות"),
    ("need_variable", "מצרכי יסוד לבית (למשל: נייר טואלט, נורות)", "ריהוט וציוד לבית"),
    ("need_variable", "תיקונים דחופים בבית (לא שיפוצים)", "תחזוקת הדירה"),
    ("need_variable", 'דו"חות וקנסות', "שונות"),
    ("need_variable", 'ייעוץ מקצועי חיוני (רו"ח, עו"ד, פסיכולוג...)', "בריאות"),
    ("need_variable", "הוצאות חיוניות על ילדים ותינוקות", "שונות"),
    ("need_variable", 'אחר (בלת"ם, מקרה חירום)', "שונות"),
    ("want_fixed", "ביטוח רכב (חודשי)", "תחבורה ותקשורת"),
    ("want_fixed", "טסט לרכב (חודשי)", "תחבורה ותקשורת"),
    ("want_fixed", "ביטוחים אחרים", "שונות"),
    ("want_fixed", "טלוויזיה - כבלים / לווין", "חינוך, תרבות ובידור"),
    ("want_fixed", "תשתית אינטרנט", "תחבורה ותקשורת"),
    ("want_fixed", "ספק אינטרנט", "תחבורה ותקשורת"),
    ("want_fixed", "סלולארי", "תחבורה ותקשורת"),
    ("want_fixed", "חוגים לילדים", "חינוך, תרבות ובידור"),
    ("want_fixed", "מנוי לשירותים אינטרנטיים", "חינוך, תרבות ובידור"),
    ("want_fixed", "שכר בעלי מקצוע (עוזרת, גנן)", "תחזוקת הדירה"),
    ("want_fixed", "מנוי חדר כושר", "חינוך, תרבות ובידור"),
    ("want_fixed", "מנוי לעיתון / מגזין", "חינוך, תרבות ובידור"),
    ("want_fixed", "דמי חבר אחרים", "שונות"),
    ("want_fixed", "תרומות", "שונות"),
    ("want_fixed", "מותרות קבועה אחרת", "שונות"),
    ("want_variable", "דלק לרכב", "תחבורה ותקשורת"),
    ("want_variable", "טיפולים לרכב", "תחבורה ותקשורת"),
    ("want_variable", "אוכל בחוץ (כולל מסעדות, בתי קפה, משלוחים)", "מזון"),
    ("want_variable", "חניה", "תחבורה ותקשורת"),
    ("want_variable", "אלכוהול, טבק", "מזון"),
    ("want_variable", "פאבים ומועדוני לילה", "חינוך, תרבות ובידור"),
    ("want_variable", "תרבות וספורט", "חינוך, תרבות ובידור"),
    ("want_variable", "חופשות בארץ", "חינוך, תרבות ובידור"),
    ("want_variable", 'חופשות בחו"ל', "חינוך, תרבות ובידור"),
    ("want_variable", "ביגוד, תכשיטים וקוסמטיקה", "הלבשה והנעלה"),
    ("want_variable", "רהיטים, כלי בית וגן", "ריהוט וציוד לבית"),
    ("want_variable", "שיפוץ ועיצוב הבית", "ריהוט וציוד לבית"),
    ("want_variable", "גאדג'טים ואלקטרוניקה", "ריהוט וציוד לבית"),
    ("want_variable", "מתנות", "שונות"),
    ("want_variable", "הוצאות טיפול בחיית מחמד", "שונות"),
    ("want_variable", "השכרת רכב", "תחבורה ותקשורת"),
    ("want_variable", "ספרים ומוזיקה", "חינוך, תרבות ובידור"),
    ("want_variable", "צעצועים לילדים", "חינוך, תרבות ובידור"),
    ("want_variable", "מותרות משתנה אחרת", "שונות"),
    ("saving_gross", "הפקדות לקרן השתלמות", ""),
    ("saving_gross", "הפקדות לקופת גמל", ""),
    ("saving_gross", "הפקדות לקרן פנסיה", ""),
    ("saving_gross", "הפקדות לביטוח מנהלים", ""),
    ("saving_net", "הפקדות לתכנית חיסכון בנקאית", ""),
    ("saving_net", "הפקדות לפוליסת חיסכון פיננסי", ""),
    ("saving_net", "הפקדות לתיק ההשקעות", ""),
    ("saving_net", "הפקדות לאפיק חיסכון אחר", ""),
    ("uncategorized", UNCATEGORIZED, "שונות"),
    ("excluded", INTERNAL_TRANSFER, ""),
    ("excluded", SECURITIES_LINE, ""),
    ("excluded", CARD_PAYOFF_LINE, ""),
]

# Personal-inflation groups (the "מחשבון אינפלציה אישית" sheet)
CPI_GROUPS = [
    "מזון", "דיור", "תחזוקת הדירה", "ריהוט וציוד לבית", "הלבשה והנעלה",
    "בריאות", "חינוך, תרבות ובידור", "תחבורה ותקשורת", "שונות",
]

# Card-export merchant sector (ענף) → budget line
SECTOR_MAP = {
    "מזון ומשקאות": "מצרכי מזון",
    "מסעדות": "אוכל בחוץ (כולל מסעדות, בתי קפה, משלוחים)",
    "מזון מהיר": "אוכל בחוץ (כולל מסעדות, בתי קפה, משלוחים)",
    "רפואה ובריאות": "תרופות, בדיקות וטיפולים רפואיים",
    "ריהוט ובית": "רהיטים, כלי בית וגן",
    "ביטוח ופיננסים": "ביטוחים אחרים",
    "פנאי בילוי": "תרבות וספורט",
    "אנרגיה": "דלק לרכב",
    "מוסדות": "עמלות שירות ובירוקרטיה",
    "טיפוח ויופי": "מוצרי היגיינה",
    "שונות": "מותרות משתנה אחרת",
    "תקשורת ומחשבים": "מנוי לשירותים אינטרנטיים",
    "רכב ותחבורה": "טיפולים לרכב",
    "אופנה": "ביגוד, תכשיטים וקוסמטיקה",
    "עמותות ותרומות": "תרומות",
    "מלונאות ואירוח": "חופשות בארץ",
    "ציוד ומשרד": "גאדג'טים ואלקטרוניקה",
    "אירועים": "מתנות",
    "תיירות": 'חופשות בחו"ל',
    "תעשיה ומכירות": "מותרות משתנה אחרת",
    "מוצרי און ליין": "מותרות משתנה אחרת",
    "חינוך": "חוגים לילדים",
    "כלי עבודה ובנין": "תיקונים דחופים בבית (לא שיפוצים)",
    "ילדים": "הוצאות חיוניות על ילדים ותינוקות",
}

# (pattern, line, direction, priority) — generic Israeli merchants / bank wording
RULES = [
    # credit-card payoffs and moves between own accounts (counted elsewhere)
    ("ישראכרט", CARD_PAYOFF_LINE, "out", 50),
    ("ישראכארט", CARD_PAYOFF_LINE, "out", 50),
    ("דיינרס", CARD_PAYOFF_LINE, "out", 50),
    ("הרשאה כאל", CARD_PAYOFF_LINE, "out", 50),
    ("כ.א.ל", CARD_PAYOFF_LINE, "out", 50),
    ("מקס איט", CARD_PAYOFF_LINE, "out", 50),
    ("לאומי קארד", CARD_PAYOFF_LINE, "out", 50),
    ("אמריקן אקספרס", CARD_PAYOFF_LINE, "out", 50),
    ("כרטיסי אשראי", CARD_PAYOFF_LINE, "out", 40),
    ("נע-קניה", SECURITIES_LINE, "", 50),
    ("נע-מכירה", SECURITIES_LINE, "", 50),
    ("רכישת מטח", INTERNAL_TRANSFER, "", 50),
    ("הע.מטח", INTERNAL_TRANSFER, "", 50),
    ("פיקדון", INTERNAL_TRANSFER, "", 30),
    # housing
    ("למשכנתאות", "משכנתא / דמי שכירות", "out", 40),
    ("דיסקונט למש", "משכנתא / דמי שכירות", "out", 40),
    ("שכר דירה", "משכנתא / דמי שכירות", "out", 40),
    ("שכר דירה", "הכנסה משכירות - נטו", "in", 40),
    ('שכ"ד', "הכנסה משכירות - נטו", "in", 40),
    ("ארנונה", "ארנונה (חודשית)", "", 30),
    ("ועד הבית", "ועד בית", "", 30),
    ("ועד בית", "ועד בית", "", 30),
    ("חברת החשמל", "חשבון חשמל", "", 30),
    ("סופרגז", "חשבון גז", "", 30),
    ("אמישראגז", "חשבון גז", "", 30),
    ("פזגז", "חשבון גז", "", 30),
    ("מי אביבים", "חשבון מים וביוב", "", 30),
    ("תאגיד מים", "חשבון מים וביוב", "", 30),
    # loans
    ("הלוואה", "החזרי הלוואות", "out", 30),
    ("הלואה", "החזרי הלוואות", "out", 30),
    # cash & fees
    ("הפקדת מזומן", "הכנסה אחרת / חד פעמית", "in", 45),
    ("כספומט", "משיכת כספים (כספומט)", "out", 30),
    ("בנקט", "משיכת כספים (כספומט)", "out", 30),
    ("סניפומט", "משיכת כספים (כספומט)", "out", 30),
    ("שיאון", "משיכת כספים (כספומט)", "out", 30),
    ("עמלת", "עמלות שירות ובירוקרטיה", "out", 30),
    ("עמלות", "עמלות שירות ובירוקרטיה", "out", 30),
    ("ריבית זכות", "ריבית ודיבידנדים - נטו", "in", 30),
    ("דיבידנד", "ריבית ודיבידנדים - נטו", "in", 30),
    ("משכורת", "שכר עבודה #1 - נטו", "in", 20),
    ("ביטוח לאומי", "קצבאות / מלגות", "in", 30),
    ("מילואים", "קצבאות / מלגות", "in", 30),
    # health, transport, telecom
    ("קרן מכבי", 'ביטוח רפואי (כולל קופ"ח)', "", 30),
    ("מכבי שירותי", 'ביטוח רפואי (כולל קופ"ח)', "", 30),
    ("כללית מושלם", 'ביטוח רפואי (כולל קופ"ח)', "", 30),
    ("מאוחדת", 'ביטוח רפואי (כולל קופ"ח)', "", 20),
    ("רב-קו", "הוצאות תחבורה ציבורית ואופניים", "", 30),
    ("רב קו", "הוצאות תחבורה ציבורית ואופניים", "", 30),
    ("מוביט", "הוצאות תחבורה ציבורית ואופניים", "", 30),
    ("חניון", "חניה", "", 30),
    ("אחוזות החוף", "חניה", "", 30),
    ("פנגו", "חניה", "", 30),
    ("סלופארק", "חניה", "", 30),
    ("פרטנר", "סלולארי", "", 30),
    ("סלקום", "סלולארי", "", 30),
    ("פלאפון", "סלולארי", "", 30),
    ("גולן טלקום", "סלולארי", "", 30),
    ("בזק", "תשתית אינטרנט", "", 30),
    ("NETFLIX", "מנוי לשירותים אינטרנטיים", "", 30),
    ("SPOTIFY", "מנוי לשירותים אינטרנטיים", "", 30),
    ("WOLT", "אוכל בחוץ (כולל מסעדות, בתי קפה, משלוחים)", "", 30),
    ("תן ביס", "אוכל בחוץ (כולל מסעדות, בתי קפה, משלוחים)", "", 30),
    ("ביטוח חיים", "ביטוחים אחרים", "", 30),
    ("ביטוח רכב", "ביטוח רכב (חודשי)", "", 30),
    ("ביטוח דירה", "ביטוח דירה", "", 30),
]


def seed(db: Session) -> None:
    """Inserts seed rows that don't exist yet. Never overwrites user edits."""
    existing_lines = {line.name for line in db.scalars(select(BudgetLine))}
    for i, (group, name, cpi) in enumerate(BUDGET_LINES):
        if name not in existing_lines:
            db.add(BudgetLine(name=name, group=group, sort=i, cpi_group=cpi))

    existing_sectors = {m.sector for m in db.scalars(select(SectorMap))}
    for sector, line in SECTOR_MAP.items():
        if sector not in existing_sectors:
            db.add(SectorMap(sector=sector, line=line))

    if db.scalar(select(CategoryRule).limit(1)) is None:
        for pattern, line, direction, priority in RULES:
            db.add(CategoryRule(pattern=pattern, category=line, direction=direction, priority=priority))
    else:
        upgrade_rules(db)
    db.commit()


def upgrade_rules(db: Session) -> None:
    """Brings an existing DB up to the current seed rules: moves default internal-transfer rules for card
    payoffs and securities to their own lines, and adds missing seed patterns. User-edited rules are kept."""
    existing = {(r.pattern, r.direction): r for r in db.scalars(select(CategoryRule))}
    for pattern, line, direction, priority in RULES:
        rule = existing.get((pattern, direction))
        if rule is None:
            if line in (SECURITIES_LINE, CARD_PAYOFF_LINE):
                db.add(CategoryRule(pattern=pattern, category=line, direction=direction, priority=priority))
        elif rule.category == INTERNAL_TRANSFER and line in (SECURITIES_LINE, CARD_PAYOFF_LINE):
            rule.category = line
