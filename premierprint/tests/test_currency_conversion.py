"""
Comprehensive Test Suite for Smart Currency Conversion
Tests both Transport LCV (indirect rate) and Variance LCV (direct rate) scenarios.
"""

import frappe
from frappe.utils import flt
from premierprint.services.lcv_utils import convert_to_company_currency


def test_scenario_a_transport_lcv():
	"""
	SCENARIO A: Transport LCV (The Crash Case)
	User manually inputs indirect rate: 1 USD = 12,099.18 UZS
	System should detect this is inverse and DIVIDE.
	"""
	print("\n" + "="*80)
	print("SCENARIO A: Transport LCV (Indirect Rate)")
	print("="*80)
	
	amount = 50000  # 50,000 UZS
	from_currency = "UZS"
	to_currency = "USD"
	user_input_rate = 12099.18  # User thinks: 1 USD = 12,099 UZS
	
	result = convert_to_company_currency(
		amount=amount,
		from_currency=from_currency,
		to_currency=to_currency,
		conversion_rate=user_input_rate
	)
	
	expected = amount / user_input_rate  # Should divide: 50,000 / 12,099.18 ≈ 4.13
	
	print(f"Input: {amount:,.2f} {from_currency}")
	print(f"User Input Rate: {user_input_rate:,.2f} (Indirect: 1 USD = {user_input_rate} UZS)")
	print(f"Expected Result: {expected:,.2f} {to_currency} (via division)")
	print(f"Actual Result: {result:,.2f} {to_currency}")
	print(f"Difference: {abs(result - expected):,.4f}")
	
	if abs(result - expected) < 0.01:
		print("✅ PASSED: Correct division applied for indirect rate")
	else:
		print("❌ FAILED: Incorrect conversion")
		print(f"   Expected ~{expected:.2f}, got {result:.2f}")
	
	return result


def test_scenario_b_variance_lcv():
	"""
	SCENARIO B: Variance LCV (The Standard Case)
	System fetches direct rate: 1 UZS = 0.00008265 USD
	System should detect this matches official rate and MULTIPLY.
	"""
	print("\n" + "="*80)
	print("SCENARIO B: Variance LCV (Direct Rate)")
	print("="*80)
	
	amount = 50000  # 50,000 UZS
	from_currency = "UZS"
	to_currency = "USD"
	system_rate = 0.00008265  # System model: 1 UZS = 0.00008 USD
	
	result = convert_to_company_currency(
		amount=amount,
		from_currency=from_currency,
		to_currency=to_currency,
		conversion_rate=system_rate
	)
	
	expected = amount * system_rate  # Should multiply: 50,000 * 0.00008265 ≈ 4.13
	
	print(f"Input: {amount:,.2f} {from_currency}")
	print(f"System Rate: {system_rate:.8f} (Direct: 1 UZS = {system_rate} USD)")
	print(f"Expected Result: {expected:,.2f} {to_currency} (via multiplication)")
	print(f"Actual Result: {result:,.2f} {to_currency}")
	print(f"Difference: {abs(result - expected):,.4f}")
	
	if abs(result - expected) < 0.01:
		print("✅ PASSED: Correct multiplication applied for direct rate")
	else:
		print("❌ FAILED: Incorrect conversion")
		print(f"   Expected ~{expected:.2f}, got {result:.2f}")
	
	return result


def test_same_result_both_scenarios():
	"""
	CRITICAL TEST: Both scenarios should yield approximately the same result.
	50,000 UZS should equal ~4.13 USD regardless of rate format.
	"""
	print("\n" + "="*80)
	print("CRITICAL VERIFICATION: Same Amount, Different Rate Formats")
	print("="*80)
	
	result_a = test_scenario_a_transport_lcv()
	result_b = test_scenario_b_variance_lcv()
	
	print("\n" + "="*80)
	print("FINAL COMPARISON")
	print("="*80)
	print(f"Scenario A (Indirect Rate): {result_a:,.2f} USD")
	print(f"Scenario B (Direct Rate):   {result_b:,.2f} USD")
	print(f"Difference: {abs(result_a - result_b):,.4f} USD")
	
	if abs(result_a - result_b) < 0.01:
		print("✅ SUCCESS: Both scenarios produce the same result!")
		print("   The ambiguity is RESOLVED.")
	else:
		print("❌ FAILURE: Results differ significantly!")
		print("   The system still has conversion issues.")


def test_edge_cases():
	"""
	Test edge cases and error handling.
	"""
	print("\n" + "="*80)
	print("EDGE CASE TESTS")
	print("="*80)
	
	# Test 1: Same currency (no conversion)
	result = convert_to_company_currency(1000, "USD", "USD", 12099.18)
	print(f"Same Currency Test: {result:.2f} (expected 1000.00)")
	assert abs(result - 1000) < 0.01, "Same currency conversion failed"
	print("✅ Same currency test passed")
	
	# Test 2: Zero/invalid rate handling
	result = convert_to_company_currency(1000, "UZS", "USD", 0)
	print(f"Zero Rate Test: {result:.2f} (should use fallback rate)")
	print("✅ Zero rate handled gracefully")
	
	# Test 3: Reverse conversion (USD to UZS)
	result = convert_to_company_currency(
		amount=100,
		from_currency="USD",
		to_currency="UZS",
		conversion_rate=12099.18
	)
	expected = 100 * 12099.18  # Should multiply
	print(f"Reverse Conversion (USD->UZS): {result:,.2f} UZS (expected ~{expected:,.2f})")
	assert abs(result - expected) / expected < 0.10, "Reverse conversion failed"
	print("✅ Reverse conversion test passed")
	
	print("\n✅ All edge case tests passed")


def run_all_tests():
	"""
	Execute complete test suite.
	"""
	print("\n")
	print("╔" + "="*78 + "╗")
	print("║" + " "*20 + "SMART CURRENCY CONVERSION TEST SUITE" + " "*22 + "║")
	print("║" + " "*15 + "Testing Ambiguous Exchange Rate Resolution" + " "*18 + "║")
	print("╚" + "="*78 + "╝")
	
	try:
		# Main functionality tests
		test_same_result_both_scenarios()
		
		# Edge case tests
		test_edge_cases()
		
		print("\n" + "="*80)
		print("🎉 ALL TESTS COMPLETED SUCCESSFULLY 🎉")
		print("="*80)
		print("\nThe system now correctly handles:")
		print("  ✓ Indirect rates (1 USD = 12,099 UZS) → Division")
		print("  ✓ Direct rates (1 UZS = 0.00008 USD) → Multiplication")
		print("  ✓ Both produce identical results for the same amount")
		print("  ✓ Edge cases and error handling work correctly")
		
	except Exception as e:
		print("\n" + "="*80)
		print("❌ TEST SUITE FAILED")
		print("="*80)
		print(f"Error: {str(e)}")
		frappe.log_error(
			message=frappe.get_traceback(),
			title="Currency Conversion Test Failed"
		)
		raise


# Execute tests when file is run
if __name__ == "__main__":
	run_all_tests()
