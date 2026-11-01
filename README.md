# server-app-progeficaz

## Configuração

Copie `.env.example` para `.env` e configure `MONGO_URI`, `DB_NAME` e
`JWT_SECRET_KEY`. O segredo JWT deve ser aleatório e privado; a aplicação recusa
iniciar quando ele não está definido ou contém apenas espaços.

A inicialização cria um índice único em `users.email`. Se já houver documentos
com e-mails duplicados, resolva os conflitos antes de iniciar a aplicação; nenhum
documento é removido automaticamente.

As senhas aceitam até 72 bytes em UTF-8, limite do bcrypt. Caracteres acentuados
podem ocupar mais de um byte. Senhas acima do limite retornam HTTP 400 no cadastro
e HTTP 401 no login, com a mesma mensagem de credenciais inválidas.

## Testes

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

Os testes usam uma coleção simulada e não acessam o MongoDB configurado no `.env`.
