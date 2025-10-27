"""
Tests for Paynow client
"""

from app.utils.paynow_client import PaynowClient


def test_hash_generation():
    """Test hash generation with Paynow example"""
    # Example from Paynow docs
    client = PaynowClient(
        integration_id="1201",
        integration_key="3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977",
        result_url="http://example.com/result"
    )

    values = {
        "id": "1201",
        "reference": "TEST REF",
        "amount": "99.99",
        "additionalinfo": "A test ticket transaction",
        "returnurl": "http://www.google.com/search?q=returnurl",
        "resulturl": "http://www.google.com/search?q=resulturl",
        "status": "Message"
    }

    expected_hash = "2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689"

    generated_hash = client.generate_hash(values)

    assert generated_hash == expected_hash, f"Expected {expected_hash}, got {generated_hash}"


def test_hash_validation():
    """Test hash validation"""
    client = PaynowClient(
        integration_id="1201",
        integration_key="3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977",
        result_url="http://example.com/result"
    )

    # Valid payload with correct hash
    payload = {
        "status": "Ok",
        "browserurl": "https://staging.paynow.co.zw/Payment/ConfirmPayment/9510",
        "pollurl": "https://staging.paynow.co.zw/Interface/CheckPayment/?guid=c7ed41da-0159-46da-b428-69549f770413",
        "paynowreference": "9510",
        "hash": "750DD0B0DF374678707BB5AF915AF81C228B9058AD57BB7120569EC68BBB9C2EFC1B26C6375D2BC562AC909B3CD6B2AF1D42E1A5E479FFAC8F4FB3FDCE71DF4D"
    }

    assert client.validate_hash(payload) == True

    # Invalid hash
    payload["hash"] = "INVALID_HASH"
    assert client.validate_hash(payload) == False


if __name__ == "__main__":
    print("Testing hash generation...")
    test_hash_generation()
    print("✅ Hash generation test passed")

    print("Testing hash validation...")
    test_hash_validation()
    print("✅ Hash validation test passed")
