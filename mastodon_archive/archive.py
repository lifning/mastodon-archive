#!/usr/bin/env python3
# Copyright (C) 2017-2019  Alex Schroeder <alex@gnu.org>
# Copyright (C) 2017       Steve Ivy <steveivy@gmail.com>

# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.

import sys
import os.path
from . import core

def archive(args):
    """
    Archive your toots, favourites, and bookmarks from your Mastodon account
    """

    skip_favourites = args.skip_favourites
    skip_bookmarks = args.skip_bookmarks
    with_mentions = args.with_mentions
    with_followers = args.with_followers
    with_following = args.with_following
    stopping = args.stopping

    (username, domain) = core.parse(args.user)

    status_file = domain + '.user.' + username + '.json'
    data = core.load(status_file)

    mastodon = core.login(args)

    print("Get user info")

    try:
        user = mastodon.account_verify_credentials()
    except Exception as e:
        if "access token was revoked" in str(e):
            core.deauthorize(args)
             # retry and exit without an error
            archive(args)
            sys.exit(0)
        elif "Name or service not known" in str(e):
            print("Error: the instance name is either misspelled or offline",
              file=sys.stderr)
        else:
            print(e, file=sys.stderr)
        # exit in either case
        sys.exit(1)

    def complete(statuses, page, func = None):
        """
        Why aren't we using Mastodon.fetch_remaining(first_page)? It
        requires some metadata for the next request to be known. This
        is what the documentation says about
        Mastodon.fetch_next(previous_page): "Pass in the previous page
        in its entirety, or the pagination information dict returned
        as a part of that pages last status (‘_pagination_next’)."
        When we last updated our archive, however, there was no next
        page: we got all the pages there were. So the archive will
        have a ton of _pagination_prev keys but no _pagination_next
        keys. That's why we fetch it all over again. Expiry helps,
        obviously.
        """
        seen = { str(status["id"]): status for status in statuses if status is not None }
        progress = core.progress_bar()

        # define function such that we can return from the inner and
        # from the outer loop
        def process(page):
            count = 0
            duplicates = 0
            while len(page) > 0:
                progress()
                for item in page:
                    status = item
                    # possibly a notification containing a status
                    if "status" in item:
                        status = item["status"]
                    if status and "id" in status:
                        id = str(status["id"])
                        if not id in seen:
                            if func is None or func(item):
                                seen["id"] = status
                                statuses.insert(count, status)
                                count = count + 1
                        else:
                            duplicates = duplicates + 1
                            if duplicates > 10 and stopping:
                                print() # at the end of the progress bar
                                print("Seen 10 duplicates, stopping now.")
                                print("Use --no-stopping to prevent this.")
                                return count
                try:
                    page = mastodon.fetch_next(page)
                except:
                    import time
                    print(f'\n{page.__dict__}\nfound a problem! trying to shorten the list to skip over it')
                    for i in range(19):
                        try:
                            page._pagination_next['limit'] = 20 - i
                            page = mastodon.fetch_next(page)
                            print(f'solved by reducing limit to {20-i}')
                            break
                        except:
                            time.sleep(1)
                    else:
                        print(f"couldn't shorten the list to skip it, trying to decrease max_id")
                        for i in range(5000):
                            page._pagination_next['limit'] = 1
                            page._pagination_next['max_id'] -= 1
                            try:
                                page = mastodon.fetch_next(page)
                                print(f'solved by reducing max_id to {page._pagination_next["max_id"]}')
                                page._pagination_next['limit'] = None
                                break
                            except:
                                time.sleep(1)
                        else:
                            print()
                            import traceback, json, pdb
                            traceback.print_exc()
                            pdb.post_mortem()
                            sys.exit(1)
                if page is None:
                    print() # at the end of the progress bar
                    return count
            # if len(page) was 0
            return count

        count = process(page)
        print("Added a total of %d new items" % count)
        return statuses

    def keep_mentions(notifications):
        return [x.status for x in notifications if x.type == "mention"]

    if data is None or not "statuses" in data or len(data["statuses"]) == 0:
        print("Get all statuses (this may take a while)")
        statuses = mastodon.account_statuses(user["id"], limit=100)
        statuses = mastodon.fetch_remaining(
            first_page = statuses)
    else:
        print("Get new statuses")
        statuses = complete(data["statuses"], mastodon.account_statuses(user["id"], limit=100))

    if skip_favourites:
        print("Skipping favourites")
        if data is None or not "favourites" in data:
            favourites = []
        else:
            favourites = data["favourites"]
    elif data is None or not "favourites" in data or len(data["favourites"]) == 0:
        print("Get favourites (this may take a while)")
        favourites = complete([], mastodon.favourites())
    else:
        print("Get new favourites")
        favourites = complete(data["favourites"], mastodon.favourites())

    try:
        if skip_bookmarks:
            print("Skipping bookmarks")
            if data is None or not "bookmarks" in data:
                bookmarks = []
            else:
                bookmarks = data["bookmarks"]
        elif data is None or not "bookmarks" in data or len(data["bookmarks"]) == 0:
            print("Get bookmarks (this may take a while)")
            bookmarks = complete([], mastodon.bookmarks())
        else:
            print("Get new bookmarks")
            bookmarks = complete(data["bookmarks"], mastodon.bookmarks())
    except AttributeError as e:
        bookmarks = []
        print("Skipping bookmarks since your Mastodon.py library is too old!")
        print("You might have a file called upgrade_python-mastodon.sh on your system.")
        print("Find it for example using 'locate upgrade_python-mastodon.sh' and then run it")
        print("to attempt an upgrade in-place: 'bash /path/to/upgrade_python-mastodon.sh'")
        print("If you don't have 'locate' installed, try to use 'find' to find the script:")
        print("'find / -name upgrade_python-mastodon.sh'")

    if not with_mentions:
        print("Skipping mentions")
        if data is None or not "mentions" in data:
            mentions = []
        else:
            mentions = data["mentions"]
    elif data is None or not "mentions" in data or len(data["mentions"]) == 0:
        print("Get notifications and look for mentions (this may take a while)")
        notifications = mastodon.notifications(limit=100)
        notifications = mastodon.fetch_remaining(
            first_page = notifications)
        mentions = keep_mentions(notifications)
    else:
        print("Get new notifications and look for mentions")
        is_mention = lambda x: "type" in x and x["type"] == "mention"
        mentions = complete(data["mentions"], mastodon.notifications(limit=100), is_mention)

    if not with_followers:
        print("Skipping followers")
        if data is None or not "followers" in data:
            followers = []
        else:
            followers = data["followers"]
    else:
        print("Get followers (this may take a while)")
        followers = mastodon.account_followers(user.id, limit=100)
        followers = mastodon.fetch_remaining(
            first_page = followers)

    if not with_following:
        print("Skipping following")
        if data is None or not "following" in data:
            following = []
        else:
            following = data["following"]
    else:
        print("Get following (this may take a while)")
        following = mastodon.account_following(user.id, limit=100)
        following = mastodon.fetch_remaining(
            first_page = following)

    data = {
        'account': user,
        'statuses': statuses,
        'favourites': favourites,
        'bookmarks': bookmarks,
        'mentions': mentions,
        'followers': followers,
        'following': following,
    }

    print("Saving %d statuses, %d favourites, %d bookmarks, %d mentions, %d followers, and %d following" % (
        len(statuses),
        len(favourites),
        len(bookmarks),
        len(mentions),
        len(followers),
        len(following)))

    core.save(status_file, data)
