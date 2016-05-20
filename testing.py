def make_venv_in_tempdir(tmpdir, name='venv'):
    venv = tmpdir.mkdir(name)
    venv.mkdir('child-dir')
    venv.join('banner').write('aactivating...\n')
    venv.join('.activate.sh').write('''\
cat banner
alias echo='echo "(aliased)"'
''')
    venv.join('.deactivate.sh').write('echo deactivating...\nunalias echo\n')
    return venv
