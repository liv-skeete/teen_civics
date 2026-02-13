# Subject Tags System Architecture Plan

**Status:** Architecture & Design Document (No Code Implementation)  
**Created:** 2026-02-13  
**Scope:** Invisible subject tags for bills, foundation for future mailing list  

---

## 1. Executive Summary

This document outlines the design for adding **invisible subject tags** to congressional bills in TeenCivics. Tags serve two purposes:

1. **Search Enhancement:** Enable users to find bills by category (e.g., searching "military" or "defense" finds bills tagged `defense-military`)
2. **Mailing List Foundation:** Enable future subscribers to opt into specific bill categories (e.g., "Subscribe to Education & Youth bills only")

### Design Principles

- **Fixed taxonomy of 14 categories** (12 AI-assignable + 2 system-only)
- **1-3 tags per bill** (optional; leave empty if no fit, or use `miscellaneous` fallback)
- **AI-assigned during daily pipeline** via enhanced prompt in summarizer
- **Fully searchable** via split keywords and FTS indexes
- **Admin-editable** in the existing bill summary editor
- **Zero user-facing exposure** (tags never displayed on site)
- **Backward-compatible** with existing bills (no backfill required)

---

## 2. Database Schema Changes

### 2.1 Bills Table Enhancement

**Location:** [`src/database/connection.py:init_db_tables()`](src/database/connection.py:426)

The `tags` column already exists in the bills table. Currently defined as:
```sql
tags TEXT
```

**No schema migration required.** The column is sufficient to store comma-separated tag slugs. However, we should add an index for performance:

**New Index to Add:**
```sql
CREATE INDEX IF NOT EXISTS idx_bills_tags ON bills USING GIN (string_to_array(tags, ','));
```

This GIN index enables fast `tags @> ARRAY['tag1']` queries. Alternatively, for simpler LIKE queries on the tags column:
```sql
CREATE INDEX IF NOT EXISTS idx_bills_tags_like ON bills (tags);
```

**Recommendation:** Use the LIKE index for now (simpler, sufficient for search queries). Add GIN index if tag-based filtering becomes common in future queries.

### 2.2 Tag Taxonomy Storage

Create a new canonical taxonomy module at [`src/utils/tag_taxonomy.py`](src/utils/tag_taxonomy.py) (new file):

```python
# Fixed taxonomy definition
TAG_TAXONOMY = {
    # AI-Assignable Categories (12)
    "economy-finance": "Economy & Finance",
    "climate-environment": "Climate & Environment",
    "education-youth": "Education & Youth",
    "health-healthcare": "Health & Healthcare",
    "civil-rights-justice": "Civil Rights & Justice",
    "immigration": "Immigration",
    "defense-military": "Defense & Military",
    "technology-privacy": "Technology & Privacy",
    "agriculture-food": "Agriculture & Food",
    "energy": "Energy",
    "foreign-policy": "Foreign Policy",
    "government-elections": "Government & Elections",
    
    # System-Only Categories (2)
    "all-bills": "All Bills (Mailing List)",
    "miscellaneous": "Miscellaneous",
}

# Searchable keywords for each tag (for user search enhancement)
TAG_SEARCH_ALIASES = {
    "economy-finance": ["economy", "finance", "economic", "financial", "business", "trade", "banking", "inflation", "unemployment"],
    "climate-environment": ["climate", "environment", "environmental", "green", "pollution", "emissions", "global warming", "conservation"],
    "education-youth": ["education", "youth", "schools", "student", "college", "loan", "scholarship", "university"],
    "health-healthcare": ["health", "healthcare", "medical", "doctor", "hospital", "medicine", "vaccine", "mental health"],
    "civil-rights-justice": ["civil rights", "justice", "discrimination", "equity", "equality", "voting rights", "lgbtq"],
    "immigration": ["immigration", "immigrants", "deportation", "visa", "border", "refugee"],
    "defense-military": ["defense", "military", "armed forces", "pentagon", "troops", "veterans", "warfare"],
    "technology-privacy": ["technology", "privacy", "cybersecurity", "tech", "internet", "social media", "data", "encryption"],
    "agriculture-food": ["agriculture", "farming", "farm", "food", "crop", "livestock", "rural"],
    "energy": ["energy", "oil", "gas", "solar", "wind", "nuclear", "renewable"],
    "foreign-policy": ["foreign policy", "international", "diplomacy", "trade", "sanctions", "allies"],
    "government-elections": ["government", "elections", "voting", "congress", "senate", "representative", "democracy"],
}

# Maximum tags per bill
MAX_TAGS_PER_BILL = 3

# AI-Assignable tags (everything except system-only)
AI_ASSIGNABLE_TAGS = set(TAG_TAXONOMY.keys()) - {"all-bills", "miscellaneous"}

def get_display_name(tag_slug: str) -> str:
    """Return human-readable display name for a tag."""
    return TAG_TAXONOMY.get(tag_slug, tag_slug)

def is_valid_tag(tag_slug: str) -> bool:
    """Check if tag_slug exists in taxonomy."""
    return tag_slug in TAG_TAXONOMY

def get_search_aliases(tag_slug: str) -> list:
    """Get searchable keywords for a tag."""
    return TAG_SEARCH_ALIASES.get(tag_slug, [])
```

**Rationale:**
- Centralized taxonomy prevents inconsistencies
- Search aliases enable "military" search to find `defense-military` bills
- Taxonomy can be imported by summarizer, search, and admin modules

---

## 3. AI Tagging Integration

### 3.1 Summarizer Prompt Enhancement

**Location:** [`src/processors/summarizer.py:_build_enhanced_system_prompt()`](src/processors/summarizer.py:46)

**Current Behavior:**
- Generates `overview`, `detailed`, and `tweet` summaries
- Extracts `teen_impact_score` via regex from detailed summary

**Enhancement:**
Add a section to the system prompt that instructs Claude to assign up to 3 tags from the fixed taxonomy. The prompt should:

1. List the 12 AI-assignable categories with brief definitions
2. Explain that up to 3 tags should be assigned based on bill content
3. State that `miscellaneous` should only be used if bill fits none of the 12 categories
4. Instruct Claude to output tags as a JSON array in the response

**Example Prompt Addition:**
```
**SUBJECT TAGS (NEW):**
After your summary sections, include a 'tags' key with an array of up to 3 category tags.
Only assign tags from these 12 categories. If the bill doesn't fit any category, return empty array (not 'miscellaneous').
Use 'miscellaneous' ONLY if the bill is substantive but genuinely doesn't fit the 12 categories.

Available tags:
- economy-finance: Economic policy, financial markets, banking, trade
- climate-environment: Climate action, environmental protection, conservation
- education-youth: Schools, colleges, student loans, youth programs
- health-healthcare: Medical policy, healthcare systems, public health
- civil-rights-justice: Civil rights, anti-discrimination, voting rights, equity
- immigration: Immigration policy, border security, refugee policy
- defense-military: Military policy, national defense, veterans benefits
- technology-privacy: Tech regulation, data privacy, cybersecurity, AI
- agriculture-food: Farm policy, food safety, rural development
- energy: Energy policy, renewable energy, fossil fuels
- foreign-policy: International relations, trade agreements, diplomacy
- government-elections: Electoral law, government structure, democracy

Return tags as: "tags": ["tag1-slug", "tag2-slug"]
```

### 3.2 Response Parsing

**Location:** [`src/processors/summarizer.py:summarize_bill_enhanced()`](src/processors/summarizer.py) (modify return handling)

**Expected JSON Structure (from Claude):**
```json
{
  "overview": "...",
  "detailed": "...",
  "tweet": "...",
  "tags": ["economy-finance", "government-elections"]
}
```

**Parsing Logic:**
1. Parse the JSON response from Claude
2. Extract `tags` array
3. Validate each tag against `TAG_TAXONOMY`
4. Keep only valid tags; discard invalid ones
5. Limit to `MAX_TAGS_PER_BILL` (3)
6. Convert array to comma-separated string: `"economy-finance,government-elections"`
7. Return as part of bill data dict for insertion

### 3.3 Orchestrator Integration

**Location:** [`src/orchestrator.py:process_single_bill()`](src/orchestrator.py:228)

**Current Flow:**
```
fetch_and_enrich_bills()
  ↓
summarize_bill_enhanced()  ← Returns {overview, detailed, teen_impact_score}
  ↓
insert_bill()  ← Stores to database
```

**Enhanced Flow:**
```
fetch_and_enrich_bills()
  ↓
summarize_bill_enhanced()  ← Returns {overview, detailed, teen_impact_score, tags}
  ↓
validate_and_format_tags()  ← New helper function
  ↓
insert_bill(bill_data)  ← bill_data['tags'] now populated
```

**New Helper Function:** `validate_and_format_tags(tags_array: list) -> str`
- Input: `["economy-finance", "government-elections"]` from Claude
- Validation: Check against `TAG_TAXONOMY.keys()`
- Formatting: Join to `"economy-finance,government-elections"`
- Fallback: Return empty string if all tags invalid
- Output: String ready for database insertion

### 3.4 Error Handling

- If Claude doesn't return `tags` key: leave field empty (graceful degradation)
- If tags array is empty: store empty string in database
- If tags contain invalid values: filter them out silently
- Logging: Log all tag assignments for debugging

---

## 4. Search Integration

### 4.1 Tag-Based Search Enhancement

**Location:** [`src/database/db.py:_search_tweeted_bills_like()`](src/database/db.py:711)

**Enhancement:** Extend LIKE search to include tag matching

**Current LIKE search logic:**
```python
like_clauses.append(f"""
    (LOWER(COALESCE(title, '')) LIKE %({param_name})s OR
     LOWER(COALESCE(summary_long, '')) LIKE %({param_name})s OR
     LOWER(COALESCE(sponsor_name, '')) LIKE %({param_name})s)
""")
```

**Enhanced logic:**
```python
like_clauses.append(f"""
    (LOWER(COALESCE(title, '')) LIKE %({param_name})s OR
     LOWER(COALESCE(summary_long, '')) LIKE %({param_name})s OR
     LOWER(COALESCE(sponsor_name, '')) LIKE %({param_name})s OR
     LOWER(COALESCE(tags, '')) LIKE %({param_name})s)
""")
```

This enables:
- Searching "military" finds bills tagged `defense-military` (contains "military")
- Searching "defense" finds bills tagged `defense-military` (contains "defense")
- Searching "economy" finds bills tagged `economy-finance` (contains "economy")

### 4.2 Search Alias Mapping (Future Enhancement)

**Design consideration for Phase 2:**

When implementing mailing list, add explicit tag filtering endpoint:
```
GET /api/bills?tag=economy-finance&tag=education-youth
```

For now, keyword-based LIKE search is sufficient.

### 4.3 Search Bar Placeholder Update

**Location:** [`templates/archive.html:23`](templates/archive.html:23)

**Current:**
```html
placeholder="Search by bill ID, title, sponsor, or keywords"
```

**Updated:**
```html
placeholder="Search by subject, sponsor, bill ID, or keywords"
```

This signals to users that subject-based search is supported.

### 4.4 FTS Index Enhancement (Optional)

**Location:** [`src/database/connection.py:init_db_tables()`](src/database/connection.py:462)

For better FTS support of tags, consider updating the FTS vector trigger to include tags:

**Current FTS trigger (if implemented):**
Builds tsvector from title, summary_long, etc.

**Enhanced trigger:**
Include tags column in FTS vector so searches also match full tag display names:
```sql
UPDATE bills SET fts_vector = 
  to_tsvector('english', 
    COALESCE(title, '') || ' ' ||
    COALESCE(summary_long, '') ||
    ' ' || COALESCE(tags, '')
  )
WHERE updated_at > NOW() - INTERVAL '1 minute'
```

**Note:** This requires a trigger update. For MVP, LIKE search on tags is sufficient.

---

## 5. Admin Panel Changes

### 5.1 Admin UI Enhancement

**Location:** [`templates/admin/bill_summary.html`](templates/admin/bill_summary.html)

**Current Admin Form Fields:**
- summary_overview
- summary_detailed
- summary_long
- teen_impact_score
- status
- normalized_status

**New Form Field to Add:**

After `teen_impact_score`, add:
```html
<!-- Subject Tags -->
<div class="admin-form-group admin-form-group-wide">
  <label for="field-tags">Subject Tags (comma-separated)</label>
  <input type="text" id="field-tags" name="tags"
         value="{{ bill.tags or '' }}" 
         class="admin-input"
         placeholder="e.g., economy-finance, education-youth, government-elections"
         title="Enter tag slugs separated by commas. Max 3 tags. Valid tags: economy-finance, climate-environment, education-youth, health-healthcare, civil-rights-justice, immigration, defense-military, technology-privacy, agriculture-food, energy, foreign-policy, government-elections, miscellaneous">
</div>

<!-- Tag Reference (Help Text) -->
<div class="admin-form-group admin-form-group-wide" style="background: #f5f5f5; padding: 1rem; border-radius: 4px;">
  <p><strong>Available Tags:</strong></p>
  <ul style="margin: 0; padding-left: 20px; font-size: 0.9rem;">
    <li><code>economy-finance</code> — Economy & Finance</li>
    <li><code>climate-environment</code> — Climate & Environment</li>
    <li><code>education-youth</code> — Education & Youth</li>
    <li><code>health-healthcare</code> — Health & Healthcare</li>
    <li><code>civil-rights-justice</code> — Civil Rights & Justice</li>
    <li><code>immigration</code> — Immigration</li>
    <li><code>defense-military</code> — Defense & Military</li>
    <li><code>technology-privacy</code> — Technology & Privacy</li>
    <li><code>agriculture-food</code> — Agriculture & Food</li>
    <li><code>energy</code> — Energy</li>
    <li><code>foreign-policy</code> — Foreign Policy</li>
    <li><code>government-elections</code> — Government & Elections</li>
    <li><code>miscellaneous</code> — Miscellaneous (use only as fallback)</li>
  </ul>
</div>
```

### 5.2 Client-Side Validation (Optional)

**Location:** [`static/admin.js`](static/admin.js)

Add JavaScript validation before saving:
1. Split tags by comma
2. Trim whitespace
3. Check that each tag exists in `TAG_TAXONOMY`
4. Check count ≤ 3
5. Show user-friendly error if invalid
6. Allow admin to correct and retry

**Example validation message:**
```
"Invalid tag 'xyz'. Valid tags are: economy-finance, climate-environment, ..."
```

### 5.3 Server-Side Validation

**Location:** [`app.py` update row endpoint](app.py:1035)

When admin saves tags via `/admin/api/tables/bills/rows` POST:

1. Validate `tags` field value:
   - Parse comma-separated list
   - Check each tag against `TAG_TAXONOMY`
   - Reject request if any tag invalid
   - Return 400 error with helpful message

2. Example validation code pattern:
```python
tags_input = row_data.get('tags', '').strip()
if tags_input:
    tags_list = [t.strip() for t in tags_input.split(',')]
    invalid_tags = [t for t in tags_list if t not in TAG_TAXONOMY]
    if invalid_tags:
        return jsonify({"error": f"Invalid tags: {', '.join(invalid_tags)}"}), 400
```

### 5.4 Admin Workflow

**Current Workflow:**
1. Admin logs in to `/admin/bills`
2. Clicks bill to edit summary at `/admin/bills/<bill_id>/summary`
3. Edits summaries and teen_impact_score
4. Clicks "Save Changes"

**Enhanced Workflow (no change needed):**
1–4. Same, but now includes tags field
5. Tags are saved via same form submission to `/admin/api/tables/bills/rows`

**Note:** The `tags` field is already in `ADMIN_EDITABLE_FIELDS` in `app.py:657`, so no changes needed to the backend permissions.

---

## 6. Migration Strategy

### 6.1 Schema Changes

**Zero downtime, backward-compatible:**

1. **Index addition** (optional but recommended):
   ```sql
   CREATE INDEX IF NOT EXISTS idx_bills_tags_like ON bills (tags);
   ```
   - Can be added anytime without locking table
   - Improves search performance, but not required for MVP
   - Run during off-peak hours

2. **No column additions required** (tags column already exists)

### 6.2 Code Deployment Order

1. **Deploy summarizer changes first:**
   - Update `src/processors/summarizer.py` with tag generation prompt
   - Update `src/processors/summarizer.py` to parse and extract tags
   - Add `src/utils/tag_taxonomy.py` with taxonomy definition

2. **Deploy orchestrator changes:**
   - Update `src/orchestrator.py` to use tag validation helper

3. **Deploy database utilities:**
   - Add tag validation functions to `src/database/db.py` if needed

4. **Deploy search changes:**
   - Update LIKE search in `src/database/db.py` to include tags column
   - Optional: update FTS triggers

5. **Deploy admin UI:**
   - Update `templates/admin/bill_summary.html` with tags field
   - Update `static/admin.js` with client-side validation
   - Update `app.py` with server-side validation if needed

6. **Deploy user-facing changes:**
   - Update search placeholder in `templates/archive.html`

### 6.3 Backfill Strategy

**No backfill needed.** Old bills in database will have empty `tags` fields, which is fine:
- Search will still work (empty tags don't match anything)
- New bills from daily pipeline will have tags assigned
- Admins can manually tag old bills if needed via admin panel
- Over time, as old bills are re-edited by admins, tags will be added

**Optional:** Create a migration script to bulk-tag old bills using API calls to Claude, but this is not required for MVP.

---

## 7. Future Mailing List Hooks

### 7.1 Architecture Pattern for Mailing List

The tag system is designed to seamlessly integrate with a future mailing list. Here's how:

**Mailing List Schema (not implemented yet):**
```sql
CREATE TABLE user_subscriptions (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  unsubscribed_at TIMESTAMP,
  subscription_tags TEXT,  -- "economy-finance,education-youth"
  frequency VARCHAR(50)    -- "daily", "weekly", "immediate"
);
```

### 7.2 Mailing List Bill Selection Query

When sending a digest email, query bills matching user's tags:

```sql
SELECT bill_id, title, summary_overview
FROM bills
WHERE published = TRUE
  AND date_processed > NOW() - INTERVAL '1 day'  -- or '1 week' for weekly digest
  AND (
    -- User subscribed to "all-bills" category
    (SELECT subscription_tags FROM user_subscriptions WHERE email = %s LIMIT 1) ILIKE '%all-bills%'
    OR
    -- User subscribed to at least one tag on this bill
    EXISTS (
      SELECT 1 FROM (
        SELECT TRIM(tag) as tag FROM REGEXP_SPLIT_TO_TABLE(
          (SELECT subscription_tags FROM user_subscriptions WHERE email = %s LIMIT 1),
          ','
        ) as tag
      ) user_tags
      WHERE TRIM(tags) ILIKE CONCAT('%', user_tags.tag, '%')
    )
  )
ORDER BY date_processed DESC;
```

### 7.3 Tag-to-Mailing-List Mapping

**"all-bills" category:**
- Special category: users who subscribe get all bills
- Never assigned by AI
- Admin-only: for mailing list UX

**"miscellaneous" category:**
- Fallback for bills that don't fit other 12 categories
- Optional system category for filtering
- Can be included in mailing list subscriptions

**Implementation readiness:**
- ✅ Tags stored in database (ready for filtering)
- ✅ Tags assigned to new bills by AI (ready for categorization)
- ✅ Admin can edit tags (ready for manual categorization)
- ✅ Search includes tags (ready for discovery)
- ⏳ Mailing list feature (not yet built, but architecture supports it)

### 7.4 Unsubscribe Pattern

Users in future mailing list can:
- Unsubscribe from specific tags: `"economy-finance,education-youth"` → `"economy-finance"`
- Unsubscribe from everything: set `unsubscribed_at` timestamp
- Skip a digestion (optional feature)

---

## 8. Implementation Checklist

### Pre-Implementation
- [ ] Review this plan with stakeholders
- [ ] Approve tag taxonomy (12 categories + 2 system)
- [ ] Decide on optional enhancements (FTS, client-side validation)

### Code Changes
- [ ] Create [`src/utils/tag_taxonomy.py`](src/utils/tag_taxonomy.py) with taxonomy definition
- [ ] Update [`src/processors/summarizer.py`](src/processors/summarizer.py) to prompt Claude for tags and parse response
- [ ] Update [`src/orchestrator.py`](src/orchestrator.py) to call tag validation
- [ ] Update [`src/database/db.py`](src/database/db.py) LIKE search to include tags
- [ ] Update [`templates/admin/bill_summary.html`](templates/admin/bill_summary.html) with tags input field
- [ ] Update [`static/admin.js`](static/admin.js) with optional client-side validation
- [ ] Update [`app.py`](app.py) with server-side tag validation (if client-side validation skipped)
- [ ] Update [`templates/archive.html`](templates/archive.html:23) search placeholder
- [ ] Optional: Add index on tags column to [`src/database/connection.py`](src/database/connection.py)
- [ ] Optional: Update FTS triggers to include tags

### Testing
- [ ] Test AI tag assignment with sample bills
- [ ] Test search with tag keywords (e.g., "military" finds `defense-military`)
- [ ] Test admin panel tag editing
- [ ] Test tag validation (reject invalid tags)
- [ ] Test empty tags (bills with no tags still searchable)
- [ ] Test backward compatibility (old bills without tags)

### Deployment
- [ ] Deploy in order specified in Section 6.2
- [ ] Monitor logs for any tag parsing errors
- [ ] Verify search functionality with tags
- [ ] Confirm admin panel works with new field

### Post-Deployment Monitoring
- [ ] Track tag assignment distribution (which tags are most common?)
- [ ] Monitor search queries that include tag keywords
- [ ] Collect user feedback on search experience
- [ ] Plan for future mailing list feature

---

## 9. Data Model Summary

### Tag Storage Format

**Database column:** `bills.tags` (TEXT)

**Format:** Comma-separated slugs
```
"economy-finance,education-youth,government-elections"
```

**Null/Empty:** Empty string `""` or `NULL` if no tags assigned

### Search Query Examples

```sql
-- Find all bills tagged with economy-finance
SELECT * FROM bills 
WHERE tags LIKE '%economy-finance%'
ORDER BY date_processed DESC;

-- Find bills matching any of multiple tags
SELECT * FROM bills 
WHERE tags LIKE '%economy-finance%' 
   OR tags LIKE '%education-youth%'
ORDER BY date_processed DESC;

-- Find bills with "military" in title OR tags
SELECT * FROM bills 
WHERE LOWER(title) LIKE '%military%'
   OR LOWER(tags) LIKE '%military%'
ORDER BY date_processed DESC;
```

### API Response Example (after search)

```json
{
  "bill_id": "hr123-119",
  "title": "Defense Modernization Act",
  "summary_overview": "...",
  "tags": "defense-military,government-elections",
  "date_processed": "2026-02-13T00:00:00Z"
}
```

---

## 10. Appendix: Tag Definitions

| Slug | Display Name | Description | Example Keywords |
|------|--------------|-------------|-------------------|
| economy-finance | Economy & Finance | Economic policy, financial markets, banking, trade | economy, finance, business, trade, banking |
| climate-environment | Climate & Environment | Climate action, environmental protection, conservation | climate, environment, green, pollution, conservation |
| education-youth | Education & Youth | Schools, colleges, student loans, youth programs | education, school, college, student, youth |
| health-healthcare | Health & Healthcare | Medical policy, healthcare systems, public health | health, healthcare, medical, hospital, vaccine |
| civil-rights-justice | Civil Rights & Justice | Civil rights, anti-discrimination, voting rights, equity | civil rights, justice, discrimination, equity |
| immigration | Immigration | Immigration policy, border security, refugee policy | immigration, immigrant, border, visa, refugee |
| defense-military | Defense & Military | Military policy, national defense, veterans | defense, military, armed forces, veterans |
| technology-privacy | Technology & Privacy | Tech regulation, data privacy, cybersecurity, AI | technology, privacy, cybersecurity, tech, internet |
| agriculture-food | Agriculture & Food | Farm policy, food safety, rural development | agriculture, farming, food, crop, livestock |
| energy | Energy | Energy policy, renewable energy, fossil fuels | energy, oil, gas, solar, renewable |
| foreign-policy | Foreign Policy | International relations, trade agreements, diplomacy | foreign policy, international, diplomacy, sanctions |
| government-elections | Government & Elections | Electoral law, government structure, democracy | government, elections, voting, congress, senate |
| all-bills | All Bills (Mailing List) | Special category for subscribing to all bills | (system-only, never AI-assigned) |
| miscellaneous | Miscellaneous | Bills that don't fit other categories | (fallback for system-only) |

---

## 11. Design Decisions & Rationale

### Decision 1: Store tags as comma-separated text, not separate table

**Alternative considered:** Create `bill_tags` junction table
```sql
CREATE TABLE bill_tags (
  id SERIAL PRIMARY KEY,
  bill_id VARCHAR(50) NOT NULL,
  tag_slug VARCHAR(50) NOT NULL,
  FOREIGN KEY (bill_id) REFERENCES bills(bill_id)
);
```

**Chosen:** Comma-separated TEXT in bills table

**Rationale:**
- ✅ Simple: no JOIN needed for search
- ✅ Denormalized data fits MVP requirements (tags are immutable after AI assignment)
- ✅ Easier for admin to edit (single field)
- ✅ Sufficient for 1-3 tags per bill
- ⚠️ Not ideal if tags become highly dynamic, but they won't be

**Future migration path:** If needed later, can normalize to junction table via migration script.

---

### Decision 2: AI assigns tags in summarizer, not as separate post-processing step

**Alternative considered:** After bill is summarized and stored, make separate API call to Claude for tagging

**Chosen:** Include tagging in main summarizer prompt

**Rationale:**
- ✅ Single API call (lower latency, lower cost)
- ✅ Claude has full bill context (summary + teen impact score)
- ✅ Tags generated fresh daily, no stale data
- ✅ Aligns with existing orchestrator flow

---

### Decision 3: No backfill of old bills

**Alternative considered:** Create backfill script that tags all existing bills via Claude API

**Chosen:** Leave old bills untagged; tag future bills only

**Rationale:**
- ✅ No cost/latency impact on existing dataset
- ✅ MVP ships faster
- ✅ Admins can manually tag important old bills
- ✅ Over time, edited bills get tags via admin re-editing
- ⚠️ Search on old bills won't match tags (but still matches title/summary)

---

### Decision 4: Max 3 tags per bill

**Rationale:**
- ✅ Prevents over-tagging (bills should fit main 1-3 categories)
- ✅ Simplifies mailing list filtering logic
- ✅ Reflects reality: bills are usually focused on 1-2 topics
- ✅ Encourages quality > quantity

**Exception:** No minimum tags required (0 tags okay for edge cases)

---

### Decision 5: Search placeholder change only, no dedicated tag filter UI

**Alternative considered:** Add dropdown filter like status filter:
```html
<select name="tag">
  <option value="all">All Tags</option>
  <option value="economy-finance">Economy & Finance</option>
  ...
</select>
```

**Chosen:** Rely on keyword search + placeholder hint

**Rationale:**
- ✅ MVP simpler: no new UI component
- ✅ Keyword search more intuitive for users ("military" > dropdown selection)
- ✅ Placeholder hints that tag search exists
- ✅ Tag filter can be added in Phase 2 for mailing list feature

---

## 12. Success Metrics

After implementation, measure:

1. **Tag Coverage:** % of new bills assigned at least 1 tag (target: 85%+)
2. **Search Volume:** % of searches that include tag keywords (target: 15%+)
3. **Search Quality:** Do tag-based searches return relevant results? (manual spot-check)
4. **Admin Adoption:** % of admin edits that include tag adjustments (target: 20%+)
5. **Data Quality:** Spot-check random bills to ensure tag appropriateness

---

## 13. Known Limitations & Future Improvements

### Limitations

1. **No real-time tag updates:** Tags assigned at summarization time; can't auto-update if bill status changes later
   - Mitigation: Admins can manually edit tags as needed

2. **No tag trending/analytics:** No built-in views of which tags are most common
   - Future: Add admin dashboard showing tag distribution

3. **No tag-based sorting/filtering on archive page:** Only search-based
   - Future: Add dropdown filters for mailing list v1

4. **Limited to 12+2 categories:** Can't add new categories without code change
   - Rationale: Fixed taxonomy reduces AI confusion; user feedback can inform v2

### Future Improvements (Phase 2+)

- [ ] Tag-based email subscriptions (mailing list feature)
- [ ] Tag analytics dashboard for admins
- [ ] Tag suggestions for old bills (batch AI re-tagging)
- [ ] Tag synonyms (e.g., "defense" → "defense-military")
- [ ] Machine learning refinement of tag accuracy
- [ ] User feedback on tag relevance

---

## 14. References

### Key Files to Modify

- [`src/database/connection.py`](src/database/connection.py:426) — Add index
- [`src/database/db.py`](src/database/db.py:711) — Update search
- [`src/processors/summarizer.py`](src/processors/summarizer.py:46) — Add tagging prompt
- [`src/orchestrator.py`](src/orchestrator.py:228) — Integrate tag validation
- [`app.py`](app.py:657) — Optional validation enhancement
- [`templates/admin/bill_summary.html`](templates/admin/bill_summary.html) — Add tags field
- [`templates/archive.html`](templates/archive.html:23) — Update placeholder
- [`static/admin.js`](static/admin.js) — Optional client-side validation

### New Files to Create

- [`src/utils/tag_taxonomy.py`](src/utils/tag_taxonomy.py) — Taxonomy definition

### Documentation to Update

- Search help text (if help page exists)
- Admin guide (if exists)

---

**Document End**

---

## Questions for Stakeholder Review

1. **Are the 12 AI-assignable categories appropriate for TeenCivics users?**
   - Should any categories be split/merged?
   - Should we add/remove categories?

2. **Is 3 tags per bill the right limit?**
   - Should we allow more for complex bills?
   - Should we enforce minimum (e.g., always ≥1 tag)?

3. **Backfill strategy acceptable?**
   - Should we invest in tagging old bills now?
   - Or defer to Phase 2?

4. **Timeline:**
   - Can we integrate tagging into daily pipeline immediately?
   - Any dependencies blocking deployment?

5. **Future mailing list:**
   - When is Phase 2 (mailing list feature) estimated?
   - Does this design align with your vision?
