#!/usr/bin/env python3
"""
Test script to verify timezone conversions for the dual-scan workflow.
"""

from datetime import datetime
import pytz

def test_timezone_conversions():
    """Test that our cron schedules match the intended ET times."""
    
    print("=" * 60)
    print("TIMEZONE CONVERSION VERIFICATION")
    print("=" * 60)
    
    # Define timezones
    utc_tz = pytz.UTC
    et_tz = pytz.timezone('America/New_York')
    
    # Test morning scan: 9:00 AM ET should be 13:00 UTC (1:00 PM UTC)
    print("\n📅 MORNING SCAN TEST")
    print("-" * 60)
    
    # Create a datetime for 9:00 AM ET
    morning_et = et_tz.localize(datetime(2025, 1, 15, 9, 0, 0))
    morning_utc = morning_et.astimezone(utc_tz)
    
    print(f"Target ET time:  {morning_et.strftime('%I:%M %p ET (%Z)')}")
    print(f"Converts to UTC: {morning_utc.strftime('%H:%M UTC (%Z)')}")
    print(f"Cron schedule:   '0 13 * * *' (13:00 UTC)")
    
    if morning_utc.hour == 13 and morning_utc.minute == 0:
        print("✅ MORNING SCAN: Timezone conversion is CORRECT")
    else:
        print(f"❌ MORNING SCAN: Timezone conversion is WRONG (expected 13:00, got {morning_utc.hour:02d}:{morning_utc.minute:02d})")
    
    # Test evening scan: 10:30 PM ET should be 02:30 UTC next day
    print("\n📅 EVENING SCAN TEST")
    print("-" * 60)
    
    # Create a datetime for 10:30 PM ET
    evening_et = et_tz.localize(datetime(2025, 1, 15, 22, 30, 0))
    evening_utc = evening_et.astimezone(utc_tz)
    
    print(f"Target ET time:  {evening_et.strftime('%I:%M %p ET (%Z)')}")
    print(f"Converts to UTC: {evening_utc.strftime('%H:%M UTC (%Z) on %Y-%m-%d')}")
    print(f"Cron schedule:   '30 2 * * *' (02:30 UTC)")
    
    if evening_utc.hour == 2 and evening_utc.minute == 30:
        print("✅ EVENING SCAN: Timezone conversion is CORRECT")
    else:
        print(f"❌ EVENING SCAN: Timezone conversion is WRONG (expected 02:30, got {evening_utc.hour:02d}:{evening_utc.minute:02d})")
    
    # Test DST transitions
    print("\n📅 DAYLIGHT SAVING TIME TESTS")
    print("-" * 60)
    
    # During DST (summer): ET is UTC-4
    summer_et = et_tz.localize(datetime(2025, 7, 15, 9, 0, 0))
    summer_utc = summer_et.astimezone(utc_tz)
    print(f"\nSummer (DST): 9:00 AM ET → {summer_utc.strftime('%H:%M UTC')}")
    if summer_utc.hour == 13:
        print("✅ DST conversion correct (ET is UTC-4 during summer)")
    else:
        print(f"❌ DST conversion wrong (expected 13:00, got {summer_utc.hour:02d}:{summer_utc.minute:02d})")
    
    # During Standard Time (winter): ET is UTC-5
    winter_et = et_tz.localize(datetime(2025, 1, 15, 9, 0, 0))
    winter_utc = winter_et.astimezone(utc_tz)
    print(f"\nWinter (EST): 9:00 AM ET → {winter_utc.strftime('%H:%M UTC')}")
    if winter_utc.hour == 14:
        print("✅ EST conversion correct (ET is UTC-5 during winter)")
    else:
        print(f"⚠️  Note: During EST (winter), 9 AM ET is actually {winter_utc.hour:02d}:{winter_utc.minute:02d} UTC")
    
    print("\n" + "=" * 60)
    print("IMPORTANT NOTES:")
    print("=" * 60)
    print("• Cron schedules run in UTC and don't adjust for DST")
    print("• During EST (Nov-Mar): 9 AM ET = 14:00 UTC (not 13:00)")
    print("• During EDT (Mar-Nov): 9 AM ET = 13:00 UTC")
    print("• Current cron '0 13 * * *' will run at:")
    print("  - 9:00 AM EDT (summer)")
    print("  - 8:00 AM EST (winter)")
    print("\n• To always run at 9 AM ET regardless of DST, you need")
    print("  two separate cron schedules or dynamic scheduling.")
    print("=" * 60)

if __name__ == "__main__":
    test_timezone_conversions()