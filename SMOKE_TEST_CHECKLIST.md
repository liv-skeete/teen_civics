# TeenCivics CAC v1 - Manual Smoke Test Checklist

## Pre-Test Setup
- [ ] Ensure `.env` file has all required environment variables
- [ ] Database is accessible and contains test data
- [ ] All dependencies installed: `pip install -r requirements.txt`

## 1. Application Startup
- [ ] **Start Flask app**: `python3 app.py`
- [ ] App starts without errors
- [ ] No import errors in console
- [ ] Server listening on port 5000

## 2. Homepage Tests
- [ ] Navigate to `http://localhost:5000/`
- [ ] Page loads without errors
- [ ] Latest bill displays correctly
- [ ] Bill title, summary, and metadata visible
- [ ] Poll voting interface renders
- [ ] Navigation menu works (mobile and desktop)

## 3. Archive Page Tests
- [ ] Navigate to `/archive`
- [ ] Archive page loads
- [ ] Bills list displays
- [ ] Filter by congress works (dropdown)
- [ ] Filter by chamber works (House/Senate/Both)
- [ ] Pagination works (if applicable)
- [ ] Bill links are clickable

## 4. Bill Detail Page Tests
- [ ] Click on a bill from archive
- [ ] Bill detail page loads
- [ ] Full bill information displays
- [ ] Teen Impact Score visible
- [ ] Long summary displays
- [ ] Poll results show correctly
- [ ] Back navigation works

## 5. Static Pages Tests
- [ ] Navigate to `/resources`
- [ ] Resources page loads
- [ ] All links work
- [ ] Navigate to `/about`
- [ ] About page loads
- [ ] Navigate to `/contact`
- [ ] Contact page loads

## 6. Error Handling Tests
- [ ] Navigate to `/nonexistent-page`
- [ ] 404 page displays correctly
- [ ] 404 page has navigation back to home

## 7. Mobile Navigation Tests
- [ ] Resize browser to mobile width (<768px)
- [ ] Mobile menu icon appears
- [ ] Click mobile menu icon
- [ ] Menu opens/closes correctly
- [ ] All navigation links work on mobile

## 8. Poll Voting Tests
- [ ] On homepage or bill detail page
- [ ] Click "Support" button
- [ ] Vote registers (check console/network tab)
- [ ] Poll results update
- [ ] Try voting again (should update, not duplicate)
- [ ] Try "Oppose" button
- [ ] Vote changes correctly

## 9. Security Headers Tests
Run in terminal:
```bash
curl -I http://localhost:5000/
```
- [ ] `X-Frame-Options: SAMEORIGIN` present
- [ ] `Content-Security-Policy` present
- [ ] `X-Content-Type-Options: nosniff` present
- [ ] `X-XSS-Protection: 1; mode=block` present

## 10. Rate Limiting Tests
Run in terminal:
```bash
for i in {1..15}; do curl -X POST http://localhost:5000/api/vote -H "Content-Type: application/json" -d '{"bill_id":"test","vote_type":"support"}'; done
```
- [ ] First 10 requests succeed
- [ ] Requests 11-15 return 429 (Too Many Requests)
- [ ] Rate limit message displays

## 11. API Endpoint Tests
Test `/api/vote` endpoint:
```bash
curl -X POST http://localhost:5000/api/vote \
  -H "Content-Type: application/json" \
  -d '{"bill_id":"hr1234-118","vote_type":"support"}'
```
- [ ] Returns JSON response
- [ ] Success: `{"success": true}`
- [ ] Invalid data returns error message

## 12. Static Assets Tests
- [ ] CSS loads correctly (check browser dev tools)
- [ ] JavaScript loads correctly
- [ ] Favicon displays in browser tab
- [ ] Images load (logo, creator photo)
- [ ] No 404 errors in console for assets

## 13. Database Connection Tests
- [ ] App connects to database on startup
- [ ] Bills load from database
- [ ] Poll votes save to database
- [ ] No database connection errors in logs

## 14. Performance Tests
- [ ] Homepage loads in < 2 seconds
- [ ] Archive page loads in < 3 seconds
- [ ] Bill detail page loads in < 2 seconds
- [ ] No memory leaks (check with multiple page loads)

## 15. Browser Compatibility Tests
Test in multiple browsers:
- [ ] Chrome/Chromium
- [ ] Firefox
- [ ] Safari (if on macOS)
- [ ] Mobile Safari (if available)
- [ ] Mobile Chrome (if available)

## Post-Test Verification
- [ ] No errors in Flask console
- [ ] No JavaScript errors in browser console
- [ ] All features work as expected
- [ ] Ready for production deployment

## Notes
- Record any issues found during testing
- Note browser/OS versions tested
- Document any unexpected behavior
- Check logs for warnings or errors

## Test Results Summary
**Date Tested**: _______________
**Tested By**: _______________
**Pass/Fail**: _______________
**Issues Found**: _______________
**Ready for Deployment**: [ ] Yes [ ] No