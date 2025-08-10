import random
import string


class TransactionRefGenerator:
    def __init__(self):
        self.prefix = ["A"]
        self.suffix = "0"

    def _increment_suffix(self):
        """
        Increment the suffix alphanumerically (0-9, A-Z).
        """
        suffix = list(self.suffix)
        for i in range(len(suffix) - 1, -1, -1):
            if suffix[i] == "Z":
                suffix[i] = "0"
            elif suffix[i] == "9":
                suffix[i] = "A"
                break
            else:
                suffix[i] = chr(ord(suffix[i]) + 1)
                break
        else:
            suffix.insert(0, "0")
        self.suffix = ''.join(suffix)

    def _increment_prefix(self):
        """
        Increment the prefix alphabetically (A → B, Z → AA, etc.).
        """
        for i in range(len(self.prefix) - 1, -1, -1):
            if self.prefix[i] == "Z":
                self.prefix[i] = "A"
            else:
                self.prefix[i] = chr(ord(self.prefix[i]) + 1)
                return
        self.prefix.insert(0, "A")

    def generate(self):
        """
        Generate a unique transaction reference.
        """
        random_string = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        transaction_ref = f"{''.join(self.prefix)}{self.suffix}{random_string}"
        self._increment_suffix()

        if self.suffix == "0":
            self._increment_prefix()
        return transaction_ref

