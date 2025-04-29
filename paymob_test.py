import os
import unittest
from commerce.paymob import create_session


class PaymobIntegrationTest(unittest.TestCase):
    def test_create_session(self):
        url = create_session(1000)
        self.assertIn("https://accept.paymob.com/unifiedcheckout/", url)
        self.assertIn("?publicKey=" + 'egy_pk_test_', url)
        self.assertIn("&clientSecret=egy_csk_test_", url)
        # https://developers.paymob.com/egypt/test-credentials-1
        print(url)


if __name__ == '__main__':
    unittest.main()
