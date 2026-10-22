import unittest
from unittest.mock import patch
from datetime import date, datetime, timedelta
import biblioteca_escolar.biblioteca as biblioteca

class Operations(unittest.TestCase):
    def test_no_stock(self):
        with patch('biblioteca_escolar.biblioteca.execute',return_value=0) as execute:
            with self.assertRaises(ValueError): biblioteca.new_loan(None,1,1,date.today(),date.today())
            self.assertEqual(execute.call_count,1)

    def test_invalid_dates_do_not_change_stock(self):
        with patch('biblioteca_escolar.biblioteca.execute') as execute:
            with self.assertRaises(ValueError): biblioteca.new_loan(None,1,1,date.today(),date.today()-timedelta(days=1))
            execute.assert_not_called()

    def test_successful_loan_decrements_and_inserts(self):
        with patch('biblioteca_escolar.biblioteca.execute',return_value=1) as execute:
            biblioteca.new_loan(None,1,2,date.today(),date.today()+timedelta(days=7))
            self.assertEqual(execute.call_count,2)
            self.assertIn('disponible-1',execute.call_args_list[0].args[1])
            self.assertEqual(execute.call_args_list[1].args[2]['e'],'Activo')

    def test_double_return_rejected(self):
        with patch('biblioteca_escolar.biblioteca.query',return_value=[{'id_libro':2,'fecha_prestamo':datetime.now(),'estado':'Devuelto'}]), patch('biblioteca_escolar.biblioteca.execute') as execute:
            with self.assertRaises(ValueError): biblioteca.return_loan(None,1,date.today(),'ok',0)
            execute.assert_not_called()

    def test_return_increments_once(self):
        with patch('biblioteca_escolar.biblioteca.query',side_effect=[[{'id_libro':2,'fecha_prestamo':datetime.now(),'estado':'Activo'}],[]]),patch('biblioteca_escolar.biblioteca.execute',return_value=1) as execute:
            biblioteca.return_loan(None,1,date.today(),'ok',0)
            self.assertEqual(execute.call_count,3)
            self.assertIn('disponible,0)+1',execute.call_args_list[-1].args[1])

    def test_transaction_rollback(self):
        from contextlib import suppress
        with patch.dict('os.environ',{'DB_USER':'test','DB_PASSWORD':'test'}),patch('biblioteca_escolar.biblioteca.oracledb.connect') as connect:
            with self.assertRaises(ValueError):
                with biblioteca.db(): raise ValueError('invalid')
            connect.return_value.rollback.assert_called_once()
            connect.return_value.commit.assert_not_called()
            connect.return_value.close.assert_called_once()

    def test_csrf(self):
        client=biblioteca.app.test_client()
        self.assertEqual(client.post('/prestamos/nuevo',data={}).status_code,400)

    def test_templates_compile(self):
        for name in biblioteca.app.jinja_env.list_templates(): biblioteca.app.jinja_env.get_template(name)

if __name__=='__main__': unittest.main()
