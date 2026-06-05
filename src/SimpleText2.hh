/*--------------------------------------------------------------
 Copyright 2006 (c) by RWTH Aachen - Lehrstuhl fuer Informatik 6
 Richard Zens, Evgeny Matusov, Gregor Leusch
 ---------------------------------------------------------------

This header file is part of the MwerAlign C++ Library.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307,
USA.
*/
#ifndef SIMPLETEXT2_HH_
#define SIMPLETEXT2_HH_
#include "IOfile.hh"
#include <algorithm>
#include <cctype>
#include <deque>
#include <iostream>
#include <iterator>
#include <sstream>
#include <string>
#include <vector>

namespace TextNS
{

typedef std::vector<std::string> Sentence;
typedef std::vector<Sentence> VectorText;
typedef std::deque<Sentence> DequeText;

typedef VectorText SimpleText;

inline char mytolower(const char &c) { return std::tolower(c); }

inline std::string makelowerstring(const std::string &s)
{
    std::string rv(s);
    std::transform(rv.begin(), rv.end(), rv.begin(), mytolower);
    return rv;
}

inline Sentence makelowersent(const Sentence &s)
{
    Sentence rv(s.size());
    std::transform(s.begin(), s.end(), rv.begin(), makelowerstring);
    return rv;
}

template <class T> inline void makelowertext(const T &in, T &out)
{
    out.resize(in.size());
    std::transform(in.begin(), in.end(), out.begin(), makelowersent);
}

inline Sentence makeSent(const std::string &s)
{
    Sentence rv;
    std::istringstream is(s);
    std::copy(std::istream_iterator<std::string>(is), std::istream_iterator<std::string>(), std::back_inserter(rv));
    return rv;
}

}; // namespace TextNS

// These stream operators must be declared before the read/write templates below
// so that two-phase name lookup (e.g. under clang) can resolve them, since the
// operators live in the global namespace while their argument types are aliases
// for std:: containers and therefore won't be found via ADL.
std::istream &operator>>(std::istream &in, TextNS::Sentence &x);
std::ostream &operator<<(std::ostream &out, const TextNS::Sentence &x);

std::ostream &operator<<(std::ostream &out, const TextNS::VectorText &x);
std::istream &operator>>(std::istream &in, TextNS::VectorText &x);

std::ostream &operator<<(std::ostream &out, const TextNS::DequeText &x);
std::istream &operator>>(std::istream &in, TextNS::DequeText &x);

namespace TextNS
{

template <class T> void read(const std::string &fn, T &x)
{
    if (fn == std::string("stdin"))
        read(std::cin, x);
    else {
        Ifile in(fn);
        read(in, x);
    }
}

template <class T> void read(std::istream &in, T &x)
{
    std::string line, w;
    while (getline(in, line)) {
        std::istringstream is(line);
        x.push_back(TextNS::Sentence());
        while (is >> w)
            x.back().push_back(w);
    }
}

template <class T> void write(std::string &fn, const T &x)
{
    if (fn == std::string("stdout"))
        write(std::cout, x);
    else {
        Ofile out(fn);
        write(out, x);
    }
}

template <class T> void write(std::ostream &out, const T &x)
{
    for (typename T::const_iterator i = x.begin(); i != x.end(); ++i) {
        out << *i << "\n";
    }
    out << std::flush;
}

}; // namespace TextNS

inline TextNS::Sentence &operator+=(TextNS::Sentence &a, const TextNS::Sentence &b)
{
    a.reserve(a.size() + b.size());
    std::copy(b.begin(), b.end(), std::back_inserter(a));
    return a;
}

#endif
