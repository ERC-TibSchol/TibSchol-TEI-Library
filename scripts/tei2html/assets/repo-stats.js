// Stars and forks of the GitHub repository, shown in the footer. If the request fails, the link stays without numbers.
(function () {
  var box = document.querySelector('.repo-stats');
  if (!box) return;
  fetch('https://api.github.com/repos/ERC-TibSchol/TibSchol-TEI-Library', { headers: { Accept: 'application/vnd.github+json' } })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (d) {
      box.querySelector('[data-stat=stars]').textContent = d.stargazers_count + ' stars';
      box.querySelector('[data-stat=forks]').textContent = d.forks_count + ' forks';
      box.hidden = false;
    })
    .catch(function () { /* no numbers: the link still works */ });
})();
