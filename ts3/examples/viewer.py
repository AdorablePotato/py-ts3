#!/usr/bin/env python3

# The MIT License (MIT)
# 
# Copyright (c) 2013-2015 Benedikt Schmitt <benedikt@benediktschmitt.de>
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
from __future__ import with_statement
from __future__ import absolute_import
from pprint import pprint
import ts3
from itertools import imap


# Data
# ------------------------------------------------
__all__ = [u"ChannelTreeNode",
           u"view"]


# Classes
# ------------------------------------------------
class ChannelTreeNode(object):
    u"""
    Represents a channel or the virtual server in the channel tree of a virtual
    server. Note, that this is a recursive data structure.

    Common
    ------
    
    self.childs = List with the child *Channels*.

    self.root = The *Channel* object, that is the root of the whole channel
                tree.

    Channel
    -------
    
    Represents a real channel.
    
    self.info =  Dictionary with all informations about the channel obtained by
                 ts3conn.channelinfo

    self.parent = The parent channel, represented by another *Channel* object.

    self.clients = List with dictionaries, that contains informations about the
                   clients in this channel.

    Root Channel
    ------------
    
    Represents the virtual server itself.

    self.info = Dictionary with all informations about the virtual server
                obtained by ts3conn.serverinfo

    self.parent = None
    
    self.clients = None

    Usage
    -----
    
    >>> tree = ChannelTreeNode.build_tree(ts3conn, sid=1)

    Todo
    ----
    
    * It's not sure, that the tree is always correct sorted.
    """

    def __init__(self, info, parent, root, clients=None):
        u"""
        Inits a new channel node.

        If root is None, root is set to *self*.
        """
        self.info = info
        self.childs = list()
        
        # Init a root channel
        if root is None:
            self.parent = None
            self.clients = None
            self.root = self
            
        # Init a real channel
        else:
            self.parent = parent
            self.root = root
            self.clients = clients if clients is not None else list()
        return None
    
    @classmethod
    def init_root(cls, info):
        u"""
        Creates a the root node of a channel tree.
        """
        return cls(info, None, None, None)

    def is_root(self):
        u"""
        Returns true, if this node is the root of a channel tree (the virtual
        server).
        """
        return self.parent is None

    def is_channel(self):
        u"""
        Returns true, if this node represents a real channel.
        """
        return self.parent is not None

    @classmethod
    def build_tree(cls, ts3conn, sid):
        u"""
        Returns the channel tree from the virtual server identified with
        *sid*, using the *TS3Connection* ts3conn.
        """
        ts3conn.use(sid=sid, virtual=True)

        ts3conn.serverinfo()
        serverinfo = ts3conn.last_resp.parsed[0]
        
        ts3conn.channellist()
        channellist = ts3conn.last_resp.parsed

        ts3conn.clientlist()
        clientlist = ts3conn.last_resp.parsed
        # channel id -> clients
        clientlist = dict((cid, [client for client in clientlist \
                            if client[u"cid"] == cid])
                      for cid in imap(lambda e: e[u"cid"], channellist))

        root = cls.init_root(serverinfo)
        for channel in channellist:
            ts3conn.channelinfo(cid=channel[u"cid"])
            channelinfo = ts3conn.last_resp.parsed[0]
            # This makes sure, that *cid* is in the dictionary.
            channelinfo.update(channel)
            
            channel = cls(
                info=channelinfo, parent=root, root=root,
                clients=clientlist[channel[u"cid"]])
            root.insert(channel)
        return root

    def insert(self, channel):
        u"""
        Inserts the channel in the tree.
        """
        self.root._insert(channel)
        return None

    def _insert(self, channel):
        u"""
        Inserts the channel recursivly in the channel tree.
        Returns true, if the tree has been inserted.
        """
        # We assumed on previous insertions, that a channel is a direct child
        # of the root, if we could not find the parent. Correct this, if ctree
        # is the parent from one of these orpheans.
        if self.is_root():
            i = 0
            while i < len(self.childs):
                child = self.childs[i]
                if channel.info[u"cid"] == child.info[u"pid"]:
                    channel.childs.append(child)
                    self.childs.pop(i)
                else:
                    i += 1

        # This is not the root and the channel is a direct child of this one. 
        elif channel.info[u"pid"] == self.info[u"cid"]:
            self.childs.append(channel)
            return True

        # Try to insert the channel recursive.
        for child in self.childs:
            if child._insert(channel):
                return True

        # If we could not find a parent in the whole tree, assume, that the
        # channel is a child of the root.
        if self.is_root():
            self.childs.append(channel)
        return False

    def print(self, indent=0):
        u"""
        Prints the channel and it's subchannels recursive. If restore_order is
        true, the child channels will be sorted before printing them.
        """            
        if self.is_root():
            print u" "*(indent*3) + u"|-", self.info[u"virtualserver_name"]
        else:
            print u" "*(indent*3) + u"|-", self.info[u"channel_name"]
            for client in self.clients:
                # Ignore query clients
                if client[u"client_type"] == u"1":
                    continue
                print u" "*(indent*3+3) + u"->", client[u"client_nickname"]

        for child in self.childs:
            child.print(indent=indent + 1)
        return None


def view(ts3conn, sid=1):
    u"""
    Prints the channel tree of the virtual server, including all clients.
    """
    tree = ChannelTreeNode.build_tree(ts3conn, sid)
    tree.print()
    return None

    
# Main
# ------------------------------------------------
if __name__ == u"__main__":
    # USER, PASS, HOST, ...
    from def_param import *
    
    with ts3.query.TS3Connection(HOST, PORT) as ts3conn:
        ts3conn.login(client_login_name=USER, client_login_password=PASS)
        view(ts3conn, sid=1)
