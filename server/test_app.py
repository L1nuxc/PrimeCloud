import hashlib
import hmac
import sqlite3
import tempfile
import unittest
from pathlib import Path
import app

class LoginTest(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        app.DB=str(Path(folder.name)/"test.sqlite")
        app.TOKEN="test-token"
        app.init()
        self.db=sqlite3.connect(app.DB)
        self.addCleanup(self.db.close)
    def test_bot_exchange(self):
        device=app.challenge(self.db)
        link=device["bot"].split("=")[1]
        self.assertEqual(app.exchange(self.db, device["poll"])[0],202)
        self.assertFalse(app.confirm(self.db,device["poll"],77))
        self.assertTrue(app.confirm(self.db,link,77))
        self.assertFalse(app.confirm(self.db,link,88))
        self.assertEqual(app.exchange(self.db,link)[0],410)
        status, session=app.exchange(self.db,device["poll"])
        self.assertEqual(status,200)
        self.assertEqual(self.db.execute("select uid from sessions where token=?",(app.digest(session["token"]),)).fetchone(),(77,))
        self.assertEqual(app.exchange(self.db,device["poll"])[0],410)
    def test_widget_signature(self):
        fields={"id":"152","auth_date":str(app.utc()),"first_name":"Test"}
        def sign():
            data="\n".join(k+"="+fields[k] for k in sorted(fields) if k!="hash")
            fields["hash"]=hmac.new(hashlib.sha256(app.TOKEN.encode()).digest(),data.encode(),hashlib.sha256).hexdigest()
        sign()
        self.assertTrue(app.valid_widget(fields))
        fields["id"]="153"
        self.assertFalse(app.valid_widget(fields))
        fields["auth_date"]=str(app.utc()-400)
        sign()
        self.assertFalse(app.valid_widget(fields))
if __name__=="__main__":
    unittest.main()
