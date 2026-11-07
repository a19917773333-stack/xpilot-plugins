"""Convert newly drained cereal Events, never cached SubMaster CAN lists."""


def can_batches(events):
  result = []
  for event in events:
    if event.which() != 'can':
      continue
    result.append((int(event.logMonoTime), [(int(frame.address), bytes(frame.dat), int(frame.src))
                                          for frame in event.can]))
  return result
