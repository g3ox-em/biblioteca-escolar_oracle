import unittest
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timedelta
from werkzeug.security import generate_password_hash
import biblioteca_escolar.biblioteca as biblioteca

class Operations(unittest.TestCase):
    def test_no_stock(self):
        with patch('biblioteca_escolar.biblioteca.execute', return_value=0) as execute:
            with self.assertRaises(ValueError):
                biblioteca.new_loan(None, 1, 1, date.today(), date.today())
            self.assertEqual(execute.call_count, 1)

    def test_invalid_dates_do_not_change_stock(self):
        with patch('biblioteca_escolar.biblioteca.execute') as execute:
            with self.assertRaises(ValueError):
                biblioteca.new_loan(None, 1, 1, date.today(), date.today() - timedelta(days=1))
            execute.assert_not_called()

    def test_successful_loan_decrements_and_inserts(self):
        with patch('biblioteca_escolar.biblioteca.execute', return_value=1) as execute:
            biblioteca.new_loan(None, 1, 2, date.today(), date.today() + timedelta(days=7))
            self.assertEqual(execute.call_count, 2)
            self.assertIn('disponible-1', execute.call_args_list[0].args[1])
            self.assertEqual(execute.call_args_list[1].args[2]['e'], 'Activo')

    def test_double_return_rejected(self):
        with patch('biblioteca_escolar.biblioteca.query', return_value=[{'id_libro': 2, 'fecha_prestamo': datetime.now(), 'estado': 'Devuelto'}]), patch('biblioteca_escolar.biblioteca.execute') as execute:
            with self.assertRaises(ValueError):
                biblioteca.return_loan(None, 1, date.today(), 'ok', 0)
            execute.assert_not_called()

    def test_return_increments_once(self):
        with patch('biblioteca_escolar.biblioteca.query', side_effect=[[{'id_libro': 2, 'fecha_prestamo': datetime.now(), 'estado': 'Activo'}], []]), patch('biblioteca_escolar.biblioteca.execute', return_value=1) as execute:
            biblioteca.return_loan(None, 1, date.today(), 'ok', 0)
            self.assertEqual(execute.call_count, 3)
            self.assertIn('disponible,0)+1', execute.call_args_list[-1].args[1])

    def test_transaction_rollback(self):
        with patch.dict('os.environ', {'DB_USER': 'test', 'DB_PASSWORD': 'test'}), patch('biblioteca_escolar.biblioteca.oracledb.connect') as connect:
            with self.assertRaises(ValueError):
                with biblioteca.db():
                    raise ValueError('invalid')
            connect.return_value.rollback.assert_called_once()
            connect.return_value.commit.assert_not_called()
            connect.return_value.close.assert_called_once()

    def test_csrf(self):
        client = biblioteca.app.test_client()
        self.assertEqual(client.post('/prestamos/nuevo', data={}).status_code, 400)

    def test_templates_compile(self):
        for name in biblioteca.app.jinja_env.list_templates():
            biblioteca.app.jinja_env.get_template(name)

    def test_loan_limit_exceeded(self):
        fake_con = MagicMock()
        with patch('biblioteca_escolar.biblioteca.query', side_effect=[[{'n': 0}], [{'n': 3}]]):
            with self.assertRaises(ValueError) as ctx:
                biblioteca.new_loan(fake_con, 1, 1, date.today(), date.today() + timedelta(days=5))
            self.assertIn('límite máximo', str(ctx.exception))

    def test_overdue_student_blocked(self):
        fake_con = MagicMock()
        with patch('biblioteca_escolar.biblioteca.query', return_value=[{'n': 1}]):
            with self.assertRaises(ValueError) as ctx:
                biblioteca.new_loan(fake_con, 1, 1, date.today(), date.today() + timedelta(days=5))
            self.assertIn('atrasados', str(ctx.exception))

    def test_renew_loan_successful(self):
        fake_con = MagicMock()
        mock_row = [{'id_prestamo': 5, 'fecha_limite': date.today() + timedelta(days=2), 'estado': 'Activo'}]
        with patch('biblioteca_escolar.biblioteca.query', return_value=mock_row), patch('biblioteca_escolar.biblioteca.execute', return_value=1) as execute:
            biblioteca.renew_loan(fake_con, 5, days=7)
            self.assertEqual(execute.call_count, 1)
            self.assertIn('fecha_limite=:nl', execute.call_args[0][1])

    def test_renew_overdue_rejected(self):
        fake_con = MagicMock()
        mock_row = [{'id_prestamo': 5, 'fecha_limite': date.today() - timedelta(days=2), 'estado': 'Atrasado'}]
        with patch('biblioteca_escolar.biblioteca.query', return_value=mock_row), patch('biblioteca_escolar.biblioteca.execute'):
            with self.assertRaises(ValueError) as ctx:
                biblioteca.renew_loan(fake_con, 5, days=7)
            self.assertIn('atrasado', str(ctx.exception))

    def test_login_routes(self):
        client = biblioteca.app.test_client()
        resp = client.get('/login')
        self.assertEqual(resp.status_code, 200)

    def test_solvencia_route(self):
        client = biblioteca.app.test_client()
        fake_con = MagicMock()
        with patch('biblioteca_escolar.biblioteca.db') as mock_db, patch('biblioteca_escolar.biblioteca.query', return_value=[]):
            mock_db.return_value.__enter__.return_value = fake_con
            resp = client.get('/solvencia')
            self.assertEqual(resp.status_code, 200)

    def test_reservas_route(self):
        client = biblioteca.app.test_client()
        fake_con = MagicMock()
        with patch('biblioteca_escolar.biblioteca.db') as mock_db, patch('biblioteca_escolar.biblioteca.query', return_value=[]), patch('biblioteca_escolar.biblioteca.execute'):
            mock_db.return_value.__enter__.return_value = fake_con
            resp = client.get('/reservas')
            self.assertEqual(resp.status_code, 200)

    def test_edit_book_template_renders_inline_fields(self):
        client = biblioteca.app.test_client()
        fake_con = MagicMock()
        with patch('biblioteca_escolar.biblioteca.db') as mock_db, patch('biblioteca_escolar.biblioteca.query', return_value=[]):
            mock_db.return_value.__enter__.return_value = fake_con
            with client.session_transaction() as sess:
                sess['user'] = {'id': 1, 'usuario': 'admin', 'nombre': 'Admin', 'rol': 'ADMIN'}
            resp = client.get('/catalogo/libros/editar')
            self.assertEqual(resp.status_code, 200)
            self.assertIn('nueva_categoria', resp.get_data(as_text=True))
            self.assertIn('nuevo_autor_nombre', resp.get_data(as_text=True))

if __name__ == '__main__':
    unittest.main()
