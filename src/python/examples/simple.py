from puddle import mk_session

with mk_session('../../tests/arches/arch02.json') as session:

    a = session.input(location=None, volume=1.0)
    b = session.input(location=None, volume=1.0)
    c = session.input(location=None, volume=1.0)

    ab = session.mix(a, b)
    ab1, ab2 = session.split(ab)
    abc = session.mix(ab1, c)
    ababc = session.mix(abc, ab2)

    print(session.droplets())
