# Teen Impact Score Rubric Design

## Overview

This document provides a comprehensive scoring rubric for the Teen Impact Score system in the TeenCivics web application. The rubric is designed for AI-based evaluation (Claude AI) with conceptual guidance rather than strict mathematical formulas.

## Scoring Tiers (0-10 Scale)

### High Impact (8-10)
**Direct, immediate impact on teen daily life**
- **Education**: School funding, curriculum changes, student loan policies, college accessibility
- **Digital Life**: Social media regulation, online privacy, tech access, digital rights
- **School Policy**: Safety protocols, disciplinary procedures, extracurricular funding
- **Mental Health**: School counseling, crisis services, mental health education
- **Civic Rights**: Voting access, free speech protections, protest rights
- **Safety**: School safety measures, bullying prevention, transportation safety

### Moderate Impact (5-7)
**Significant but indirect impact through family/community**
- **Family Stability**: Parental employment, healthcare access, housing policies
- **Economic Opportunity**: Minimum wage, job training programs, apprenticeship funding
- **Public Health**: Community health services, preventive care, vaccination policies
- **Long-term Societal**: Environmental policies, infrastructure, climate change measures
- **Civic Infrastructure**: Election systems, government transparency, civic education

### Low Impact (2-4)
**Symbolic or awareness-focused with abstract teen relevance**
- **Awareness Resolutions**: Health awareness months, commemorative designations
- **Procedural Bills**: Technical corrections, administrative changes
- **Specialized Interests**: Niche policy areas with limited teen connection
- **Future-oriented**: Long-term research, pilot programs with delayed implementation

### Negligible Impact (0-1)
**Minimal or no connection to teen experience**
- **Purely Symbolic**: Honorary designations, ceremonial resolutions
- **Specialized Government**: Internal agency procedures, technical regulations
- **Adult-focused**: Retirement policies, senior benefits, specialized industry regulations
- **International**: Foreign policy with no domestic teen impact

## Category Weights & Evaluation Framework

### Weighted Categories
| Category | Weight | Description |
|----------|--------|-------------|
| **Education & School Life** | 25% | Direct impact on schools, curriculum, student resources |
| **Civic Engagement & Rights** | 25% | Voting access, free speech, protest rights, civic participation |
| **Teen Health (Mental & Physical)** | 20% | Healthcare access, mental health services, wellness programs |
| **Economic Opportunity & Family Stability** | 15% | Job opportunities, family economic security, housing stability |
| **Environment & Future Opportunities** | 10% | Climate change, environmental quality, long-term societal impact |
| **Symbolism/Awareness** | 5% | Educational value of awareness campaigns, symbolic importance |

### Evaluation Process

1. **Initial Assessment**: Review bill title, summary, and key provisions
2. **Category Evaluation**: Score each category 0-10 based on relevance and impact
3. **Weighted Calculation**: Apply category weights to calculate preliminary score
4. **Context Adjustment**: Adjust for bill type, enforcement mechanisms, and scope
5. **Final Score**: Round to nearest whole number with qualitative description

### Conceptual Formula
```
Final Score = (Education × 0.25) + (Civic × 0.25) + (Health × 0.20) + 
              (Economic × 0.15) + (Environment × 0.10) + (Symbolism × 0.05)
```

## Example Evaluations

### Health Awareness Resolutions (Score: 3-4)

**National Infant Mortality Awareness Month**
- **Score**: 3/10
- **Reasoning**: While infant mortality is an important public health issue, its direct impact on teenagers' daily lives is limited. Most teens are not parents and don't make healthcare decisions for infants. The resolution raises awareness but doesn't create programs, funding, or policy changes that directly affect teen experiences. The educational value is present but abstract.

**PCOS Awareness Month**
- **Score**: 4/10  
- **Reasoning**: Polycystic Ovary Syndrome affects many women, including teenagers. However, awareness resolutions lack concrete policy changes or resources. While the topic is relevant to teen health education, the resolution itself doesn't provide healthcare access, treatment funding, or school education programs. The impact is primarily educational rather than practical.

### Comparison to Higher-Impact Bills

**School Mental Health Funding Bill** (Score: 8/10)
- Directly funds school counselors and mental health services
- Creates tangible resources teens can access immediately
- Affects daily school experience and support systems

**Social Media Privacy Protection Act** (Score: 9/10)
- Directly regulates how platforms handle teen data
- Creates enforceable privacy protections
- Impacts daily digital life and online safety

## Implementation Guidance

### For AI Evaluation (Claude Prompt)
```python
# System prompt addition for Teen Impact Score evaluation
"""
**Teen Impact Score Evaluation Guidelines:**

Evaluate bills on a 0-10 scale considering these weighted categories:
- Education & School Life (25%): Direct impact on schools, curriculum, student resources
- Civic Engagement & Rights (25%): Voting access, free speech, protest rights, civic participation  
- Teen Health (20%): Healthcare access, mental health services, wellness programs
- Economic Opportunity (15%): Job opportunities, family economic security, housing
- Environment & Future (10%): Climate change, environmental quality, long-term impact
- Symbolism/Awareness (5%): Educational value of awareness campaigns

Score tiers:
- 8-10: Direct, immediate impact on teen daily life
- 5-7: Significant but indirect impact through family/community  
- 2-4: Symbolic/awareness with abstract teen relevance
- 0-1: Minimal or no connection to teen experience

Always provide: "Teen impact score: X/10 (brief description)"
"""
```

### Edge Case Handling

**Multi-category Bills**: When a bill spans multiple categories, evaluate each category separately and use weighted average.

**Conflicting Impacts**: If a bill has both positive and negative teen impacts, focus on net effect and scope of impact.

**Resolution Types**: Simple resolutions (SRES/HRES) typically score 1-4 unless they create substantive programs.

**Appropriations Bills**: Evaluate based on teen-relevant program funding rather than overall budget size.

## Validation & Testing

Recommended test cases for rubric validation:
- Education bills with varying scope and enforcement
- Health awareness resolutions vs. substantive healthcare legislation  
- Environmental policies with different time horizons
- Civic rights bills with different enforcement mechanisms

## Next Steps for Implementation

1. Update Claude system prompt with detailed scoring guidelines
2. Create validation dataset with example bills and expected scores
3. Implement score regeneration for existing bills using new rubric
4. Add monitoring to track scoring consistency over time
5. Consider periodic rubric refinements based on real-world performance

This rubric provides a balanced, nuanced approach to evaluating congressional bills for teen relevance while maintaining consistency and transparency in scoring.