import unittest
from alerts import WaitingPolicy


def agent(key='a', event='waiting', **extra):
    return dict(agent_key=key, event=event, project='Test', **extra)


class WaitingTests(unittest.TestCase):
    def test_initial_waiting_and_dedup(self):
        p = WaitingPolicy()
        self.assertTrue(p.update([agent()])[1])
        self.assertFalse(p.update([agent()])[1])
        p.update([agent(event='working')])
        self.assertTrue(p.update([agent()])[1])

    def test_pause_unknown_and_resume(self):
        p = WaitingPolicy()
        self.assertFalse(p.update([agent(status_known=False)])[1])
        self.assertTrue(p.update([agent()])[1])
        pending, fresh, stale = p.update([agent(collection_paused=True)])
        self.assertEqual(len(pending), 1)
        self.assertFalse(fresh)
        self.assertTrue(stale)
        self.assertFalse(p.update([agent()])[1])

    def test_new_waiting_on_resume_not_missed(self):
        p = WaitingPolicy()
        p.update([agent(event='working')])
        p.update([agent(collector_online=False)])
        self.assertTrue(p.update([agent()])[1])

    def test_multiple_and_removed(self):
        p = WaitingPolicy()
        p.update([agent()])
        pending, fresh, _ = p.update([agent(), agent('b')])
        self.assertEqual(len(pending), 2)
        self.assertTrue(fresh)
        self.assertEqual(p.update([])[0], [])
        self.assertTrue(p.update([agent()])[1])

    def test_unreliable_does_not_invent_wait(self):
        p = WaitingPolicy()
        for extra in ({'status_known':False}, {'collection_paused':True}, {'collector_online':False}):
            self.assertEqual(p.update([agent(**extra)])[0], [])


if __name__ == '__main__':
    unittest.main()
