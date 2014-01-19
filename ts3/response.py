#!/usr/bin/python3

# The MIT License (MIT)
# 
# Copyright (c) 2013 Benedikt Schmitt
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


# Modules
# ------------------------------------------------
import re

# local
try:
    from escape import TS3Escape
    from common import TS3Error
except ImportError:
    from .escape import TS3Escape
    from .common import TS3Error


# Data
# ------------------------------------------------
__all__ = ["TS3Response",
           "TS3ParserError",
           "TS3QueryResponse",
           "TS3Event"]


# Classes
# ------------------------------------------------
class TS3ParserError(TS3Error, ValueError):
    """
    Raised, if the data could not be parsed.

    * resp: The TS3Response instance
    * exc: The original exception
    """

    def __init__(self, resp, exc=None):
        self.resp = resp
        self.exc = exc
        return None

    def __str__(self):
        tmp = "The response could not be parsed! Desc: {}"
        tmp.format(self.exc)
        return tmp

    
class TS3Response(object):
    """
    Parses **ONE** response and stores it's data. If you init an instance
    with the data of more than one response, parsing will fail.

    Note, that this class is **lazy**. The response is only parsed, if you
    request an attribute, that requires a parsed version of the data.
    """

    # Matches the error *line* (with line ending)
    _ERROR_LINE = re.compile(b"error id=(.)*? msg=(.)*?\n\r")    
        
    def __init__(self, data):
        self._data = data
        self._data_bytestr = None
        self._parsed = None
        self._is_parseable = True
        # Note, that the get methods for these attributes are implemented
        # in the dedicated subclasses in this module.
        self._error = None
        self._event = None
        return None

    @property
    def data(self):
        """
        List of lines with the response.
        """
        return self._data

    @property
    def data_bytestr(self):        
        """
        The raw response as bytestring.
        """
        if self._data_bytestr is None:
            self._data_bytestr = b"".join(self._data)
        return self._data_bytestr

    @property
    def parsed(self):
        """
        The parsed response as list of dictionaries. If the response
        is not parseable, None.

        May raise *TS3ParserError*.
        """
        self._parse_data()
        return self._parsed

    # ----------- LIST EMULATION ----------

    # Only rudimentary direct read-only support.
    
    def __getitem__(self, index):
        return self.parsed[index]

    def __len__(self):
        return len(self.parsed)

    def __iter__(self):
        return iter(self.parsed)

    # ----------- PARSER ----------
    
    """
    Syntaxdiagramm
    --------------    
    Legend:
        Terminals: (b"A REGEX")
        Non-Terminals: [item]

    Syntaxdiagramm:
               
        data
        ----> [event] ---> [itemlist] ---> [error] --->
                          
        itemlist  +--------------+
        ----------|              |--->
                  +--> [item] ---+
                    ^            |
                    +---(b'|') <-+
                    
        event
        -----> (b'[A-z]') ----->

        error  +----------------------------------------+
        -------|                                        |--->
               +--> (b'error id=(.)*? msg=(.)*?\n\r') --+
               
        item
        ----> [property] --->
          ^               |
          +--  (b' ')  <--+
              
        property           +-------------------------+
        --------> [key] ---|                         |-->
                           +--> (b'=') --> [value] --+

        key
        ---> (b'[A-z]+') --->

        value
        -----> (b'[A-z]+') --->

    Output
    ------    
    The return value is then similar to this structure:
    
        [{key00: val00, key01: val01, ...}, # item 0
         {key10: val10, key11: val11, ...}, # item 1
         ...
        ]

    Hints
    -----
    * If a property has no value, the value will be set to b''.
    """

    def _parse_property(self, prop):
        """
        >>> parse_property(b'key=value')
        ('key', 'value')
        
        >>> parse_property(b'foo')
        ('foo', '')

        >>> parse_property(b'client_unique_identifier=gZ7K[...]GIik=')
        ('client_unique_identifier', 'gZ7K[...]GIik=')
        """
        prop = prop.split(b"=")
        if len(prop) == 1:
            key = prop[0]
            val = bytes()
        elif len(prop) == 2:
            key, val = prop
        else:
            key = prop[0]
            val = b"=".join(prop[1:])

        try:
            key = key.decode()
            val = val.decode()
        except UnicodeDecodeError as err:
            # Todo: - Should we simply ignore decode errors?
            #       - Is decoding reasonable?
            raise TS3ParserError(self, err)

        key = TS3Escape.unescape(key)
        val = TS3Escape.unescape(val)
        return (key, val)

    def _parse_item(self, item):
        """
        >>> parse_item(b'key0=val0 key1=val1')
        {'key0': 'val0', 'key1': 'val1'}
        """
        properties = item.split()
        properties = dict(self._parse_property(p) for p in properties)
        return properties

    def _parse_itemlist(self, itemlist):
        """
        >>> parse_itemlist(b'key00=val00 key01=val01|b'key10=val10 key11=val11')
        [{'key00': 'val00', 'key01': 'val01'},
         {'key10': 'val10', 'key11': 'val11'}]
        >>> parse_itemlist(b'key0=val0 key1=val1)
        [{'key0': 'val0', 'key1': 'val1'}]
        """
        itemlist = itemlist.split(b"|")
        itemlist = [self._parse_item(item) for item in itemlist]
        return itemlist

    def _parse_error(self, line):
        """
        Returns the parsed error line. If the line is not a valid error
        line, None is returned.

        >>> parse_error(b'error id=0 msg=ok')
        {'id': '0', 'msg': 'ok'}
        >>> parse_error(b'foobar')
        None
        """
        if not re.match(self._ERROR_LINE, line):
            raise TS3ParserError(self)
        
        line = line.split()
        error = dict(self._parse_property(line[i]) \
                     for i in range(1, len(line)))
        return error

    # Highest abstraction layer
    # -------------------------

    def _parse_query_response(self):
        """
        Parses a query response.
        """
        if len(self._data) == 2:
            self._parsed = self._parse_itemlist(self._data[0])
        else:
            self._parsed = list()
            
        self._error = self._parse_error(self._data[-1])
        return None

    def _parse_event(self):
        """
        Parses a bytestring containing an event.
        """
        tmp = self._data[0].find(b" ")
        event, itemlist = self._data[0][:tmp], self._data[0][tmp:]

        try:
            self._event = event.decode()
        except UnicodeDecodeError as err:
            raise TS3ParserError(self, err)
        
        self._parsed = self._parse_itemlist(itemlist)
        return None

    def _parse_data(self):
        """
        Parses *self._data* and saves the result in the member variables.

        This method decides, if self.data contains an event or a response.
        """
        # Return, if we already tried to parse the data.
        if not self._is_parseable:
            raise TS3ParserError(self)
        if self._parsed is not None:
            return None

        # An event has only one line.
        try:
            if not 1 <= len(self._data) <= 2:
                raise TS3ParseError(self)
            
            elif re.match(self._ERROR_LINE, self._data[-1]):
                self._parse_query_response()
            else:
                self._parse_event()
        except TS3ParserError:
            self._is_parseable = False
            raise
        else:
            self._is_parseable = True
        return None


class TS3QueryResponse(TS3Response):
    """
    Makes the error attribute available.
    """

    @property
    def error(self):
        """
        Returns a dictionary, that contains the error id and message.
        """
        self._parse_data()
        return self._error


class TS3Event(TS3Response):
    """
    Makes the event attribute available. 
    """

    @property
    def event(self):
        """
        Returns the name of the event.
        """
        self._parse_data()
        return self._event